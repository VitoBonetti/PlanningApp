from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Request
import psycopg2
import uuid
import bcrypt
from database import get_db_connection
from routers.auth import get_current_user, verify_password, require_admin, limiter
from models import UserCreateSecure, UserUpdate, PasswordChange, AdminPasswordReset, FirstAdminSetup
from websockets_manager import manager
from audit_logger import log_audit_event

router = APIRouter(tags=["Users"])


@router.get("/system/status")
def check_system_status():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'")
    count = cursor.fetchone()[0]
    conn.close()
    return {"is_setup": count > 0}


@router.post("/system/setup")
def setup_first_admin(admin: FirstAdminSetup):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'")
    if cursor.fetchone()[0] > 0:
        conn.close()
        raise HTTPException(status_code=400, detail="System is already setup.")

    salt = bcrypt.gensalt()
    hashed_pw = bcrypt.hashpw(admin.password.encode('utf-8'), salt).decode('utf-8')
    new_id = str(uuid.uuid4())

    cursor.execute(
        'INSERT INTO users (id, username, hashed_password, name, role, location, base_capacity, start_week) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)',
        (new_id, admin.username, hashed_pw, admin.name, 'admin', admin.location, 1.0, 1))
    conn.commit()
    conn.close()
    return {"message": "Admin account created successfully!"}


@router.post("/users/")
@limiter.limit("10/minute")
def create_user(u: UserCreateSecure, request: Request, background_tasks: BackgroundTasks, current_user: dict = Depends(require_admin)):
    if u.role == 'read_only':
        u.base_capacity = 0.0
    salt = bcrypt.gensalt()
    hashed_pw = bcrypt.hashpw(u.password.encode('utf-8'), salt).decode('utf-8')
    new_id = str(uuid.uuid4())
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # NEW: Added start_week
        cursor.execute(
            'INSERT INTO users (id, username, hashed_password, name, role, location, base_capacity, start_week) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)',
            (new_id, u.username, hashed_pw, u.name, u.role, u.location, u.base_capacity, u.start_week))
        conn.commit()
        conn.close()
        background_tasks.add_task(
            log_audit_event,
            user_id=current_user["id"],
            username=current_user["username"],
            action="CREATE_USER",
            resource_type="USER",
            resource_id=u.username,
            details=f"Created {u.role} account for {u.name}"
        )
        background_tasks.add_task(manager.broadcast, '{"action": "REFRESH_BOARD"}')
        return {"message": f"User {u.name} created."}
    except psycopg2.errors.UniqueViolation:
        if conn:
            conn.rollback()  # Always rollback on error
        raise HTTPException(status_code=400, detail="Username already exists.")
    finally:
        if conn:
            conn.close()


# Delete User Endpoint
@router.delete("/users/{user_id}")
@limiter.limit("5/minute")
def delete_user(user_id: str, request: Request, background_tasks: BackgroundTasks, current_user: dict = Depends(require_admin)):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM assignments WHERE user_id = %s', (user_id,))
    cursor.execute('DELETE FROM events WHERE user_id = %s', (user_id,))
    cursor.execute('DELETE FROM users WHERE id = %s', (user_id,))
    conn.commit()
    conn.close()
    background_tasks.add_task(
        log_audit_event,
        user_id=current_user["id"],
        username=current_user["username"],
        action="DELETE_USER",
        resource_type="USER",
        resource_id=user_id,
        details="Permanently deleted user account."
    )
    background_tasks.add_task(manager.broadcast, '{"action": "REFRESH_BOARD"}')
    return {"message": "User deleted."}


@router.put("/users/{user_id}")
@limiter.limit("10/minute")
def update_user(user_id: str, u: UserUpdate, request: Request, background_tasks: BackgroundTasks, current_user: dict = Depends(require_admin)):
    if u.role == 'read_only':
        u.base_capacity = 0.0
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # FIX: Removed session_token=NULL from this query so it doesn't log the admin out!
    cursor.execute(
        'UPDATE users SET name=%s, role=%s, location=%s, base_capacity=%s, start_week=%s WHERE id=%s',
        (u.name, u.role, u.location, u.base_capacity, u.start_week, user_id))
        
    conn.commit()
    conn.close()
    background_tasks.add_task(
        log_audit_event,
        user_id=current_user["id"],
        username=current_user["username"],
        action="UPDATE_USER",
        resource_type="USER",
        resource_id=user_id,
        details="Updated user account."
    )
    background_tasks.add_task(manager.broadcast, '{"action": "REFRESH_BOARD"}')
    return {"message": "User updated."}


@router.put("/users/{user_id}/reset-password")
@limiter.limit("5/minute")
def admin_reset_password(user_id: str, p: AdminPasswordReset, request: Request, background_tasks: BackgroundTasks, current_user: dict = Depends(require_admin)):
    salt = bcrypt.gensalt()
    hashed_pw = bcrypt.hashpw(p.new_password.encode('utf-8'), salt).decode('utf-8')
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET hashed_password=%s WHERE id=%s', (hashed_pw, user_id))
    conn.commit()
    conn.close()
    background_tasks.add_task(
        log_audit_event,
        user_id=current_user["id"],
        username=current_user["username"],
        action="PSW_RESET",
        resource_type="USER",
        resource_id=user_id,
        details="Password has been reset."
    )
    return {"message": "User password reset successfully."}


@router.put("/users/me/password")
@limiter.limit("5/minute")
def change_own_password(p: PasswordChange, request: Request, background_tasks: BackgroundTasks, current_user: dict = Depends(get_current_user)):
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Fetch the CURRENT password hash from the database to verify it
    cursor.execute("SELECT hashed_password FROM users WHERE id = %s", (current_user['id'],))
    row = cursor.fetchone()

    # If the user doesn't exist or the old password doesn't match, reject them!
    if not row or not verify_password(p.old_password, row[0]):
        conn.close()
        raise HTTPException(status_code=400, detail="Incorrect old password.")

    # 2. Hash the NEW password
    salt = bcrypt.gensalt()
    new_hashed_pw = bcrypt.hashpw(p.new_password.encode('utf-8'), salt).decode('utf-8')

    # 3. UPDATE the password and WIPE the session_token to log out other devices
    cursor.execute(
        'UPDATE users SET hashed_password=%s, session_token=NULL WHERE id=%s',
        (new_hashed_pw, current_user['id'])
    )
    conn.commit()
    conn.close()

    # 4. Stream the event to BigQuery!
    background_tasks.add_task(
        log_audit_event,
        user_id=current_user["id"],
        username=current_user["username"],
        action="CHANGE_PASSWORD",
        resource_type="USER",
        resource_id=current_user["id"],
        details="User successfully changed their own password."
    )

    return {"message": "Password changed successfully."}


@router.get("/users/me/notifications")
def get_my_notifications(current_user: dict = Depends(get_current_user)):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, message, type, created_at FROM notifications WHERE user_id = %s AND is_read = FALSE ORDER BY created_at DESC", (current_user['id'],))
    notifs = [{"id": r[0], "message": r[1], "type": r[2], "created_at": r[3]} for r in cursor.fetchall()]
    conn.close()
    return notifs

@router.put("/users/me/notifications/read")
def mark_notifications_read(current_user: dict = Depends(get_current_user)):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE notifications SET is_read = TRUE WHERE user_id = %s", (current_user['id'],))
    conn.commit()
    conn.close()
    return {"message": "Notifications marked as read."}

