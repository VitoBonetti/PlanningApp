from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Request
import uuid
from database import get_db_cursor
from routers.auth import get_current_user, require_admin
from models import UserCreateSecure, UserUpdate
from websockets_manager import manager
from audit_logger import log_audit_event, fetch_recent_audit_logs
from datetime import datetime, timezone

router = APIRouter(tags=["Users"])


@router.get("/system/status")
def check_system_status(cursor = Depends(get_db_cursor)):
    # This now simply checks if the board has been initialized at least once
    cursor.execute("SELECT COUNT(*) FROM users")
    count = cursor.fetchone()[0]
    return {"setup_required": count == 0}


@router.get("/system/audit")
def get_system_audit_logs(current_user: dict = Depends(require_admin)):
    """Fetches the latest security audit logs from BigQuery."""
    # We restrict this to Admins only, and pull the 5000 most recent events
    logs = fetch_recent_audit_logs(limit=5000)
    return logs


@router.post("/users/")
def create_user(u: UserCreateSecure, background_tasks: BackgroundTasks,
                current_user: dict = Depends(require_admin), cursor = Depends(get_db_cursor)):
    """
    Simplified for IAP: We just pre-provision the email in our DB.
    The user will simply log in via Google.
    """
    if u.role == 'read_only':
        u.base_capacity = 0.0

    new_id = str(uuid.uuid4())

    cursor.execute(
        '''INSERT INTO users (id, username, name, role, location, base_capacity, start_week)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)''',
        (new_id, u.username.lower(), u.name, u.role, u.location, u.base_capacity, u.start_week)
    )
    
    cursor.connection.commit()
    background_tasks.add_task(manager.broadcast, '{"action": "REFRESH_BOARD"}')

    background_tasks.add_task(
        log_audit_event,
        user_id=current_user["id"],
        username=current_user["username"],
        action="CREATE_USER",
        resource_type="USER",
        resource_id=u.username,
        details=f"Pre-provisioned {u.role} account for {u.name}"
    )
    
    return {"message": f"User {u.name} whitelisted in the database."}
    

@router.delete("/users/{user_id}")
def delete_user(user_id: str, background_tasks: BackgroundTasks, 
                current_user: dict = Depends(require_admin), cursor = Depends(get_db_cursor)):

    cursor.execute('DELETE FROM assignments WHERE user_id = %s', (user_id,))
    cursor.execute('DELETE FROM events WHERE user_id = %s', (user_id,))
    cursor.execute('DELETE FROM users WHERE id = %s', (user_id,))
    cursor.connection.commit()
    background_tasks.add_task(manager.broadcast, '{"action": "REFRESH_BOARD"}')

    background_tasks.add_task(
        log_audit_event,
        user_id=current_user["id"],
        username=current_user["username"],
        action="DELETE_USER",
        resource_type="USER",
        resource_id=user_id,
        details="Permanently deleted user account metadata."
    )
    return {"message": "User deleted from system."}


@router.put("/users/{user_id}")
def update_user(user_id: str, u: UserUpdate, background_tasks: BackgroundTasks, 
                current_user: dict = Depends(require_admin), cursor = Depends(get_db_cursor)):
    
    if u.role == 'read_only':
        u.base_capacity = 0.0
    
    cursor.execute(
        'UPDATE users SET name=%s, role=%s, location=%s, base_capacity=%s, start_week=%s WHERE id=%s',
        (u.name, u.role, u.location, u.base_capacity, u.start_week, user_id))
    cursor.connection.commit()
    background_tasks.add_task(manager.broadcast, '{"action": "REFRESH_BOARD"}')

    background_tasks.add_task(
        log_audit_event,
        user_id=current_user["id"],
        username=current_user["username"],
        action="UPDATE_USER",
        resource_type="USER",
        resource_id=user_id,
        details="Updated user metadata (role/capacity)."
    )
    return {"message": "User updated."}


@router.get("/users/me")
def get_my_profile(current_user: dict = Depends(get_current_user)):
    # This is what the React app calls on load to identify the user
    return current_user


@router.get("/users/me/notifications")
def get_my_notifications(current_user: dict = Depends(get_current_user), cursor = Depends(get_db_cursor)):
    cursor.execute("""
        SELECT id, message, type, created_at 
        FROM notifications 
        WHERE user_id = %s AND is_read = FALSE 
        ORDER BY created_at DESC
    """, (current_user['id'],))
    
    notifs = [{"id": r[0], "message": r[1], "type": r[2], "created_at": r[3]} for r in cursor.fetchall()]
    return notifs


@router.put("/users/me/notifications/read")
def mark_notifications_read(current_user: dict = Depends(get_current_user), cursor = Depends(get_db_cursor)):
    cursor.execute("UPDATE notifications SET is_read = TRUE WHERE user_id = %s", (current_user['id'],))
    cursor.connection.commit()
    return {"message": "Notifications marked as read."}