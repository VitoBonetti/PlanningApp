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

    # Ensure empty strings from frontend are treated as NULL
    ew = u.end_week if str(u.end_week).strip() != '' else None
    ey = u.end_year if str(u.end_year).strip() != '' else None

    # Notice: 9 parameters in the SQL, 9 parameters in the tuple!
    cursor.execute(
        '''INSERT INTO users (id, username, name, role, location, base_capacity, start_week, start_year, end_week, end_year)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)''',
        (new_id, u.username.lower(), u.name, u.role, u.location, u.base_capacity, u.start_week, u.start_year, ew, ey)
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
    """
    SOFT DELETE: Instead of destroying history, we offboard the user instantly
    by setting their end_year and end_week to today.
    """
    current_year = datetime.now().year
    current_week = datetime.now().isocalendar()[1]

    # Soft Delete: Update the end date rather than deleting the row
    cursor.execute(
        'UPDATE users SET end_year = %s, end_week = %s WHERE id = %s', 
        (current_year, current_week, user_id)
    )
    
    # We DO NOT delete their assignments or events, so historical graphs stay accurate.
    
    cursor.connection.commit()
    background_tasks.add_task(manager.broadcast, '{"action": "REFRESH_BOARD"}')

    background_tasks.add_task(
        log_audit_event,
        user_id=current_user["id"],
        username=current_user["username"],
        action="SOFT_DELETE_USER",
        resource_type="USER",
        resource_id=user_id,
        details="Offboarded user. Historical data preserved."
    )
    return {"message": "User successfully offboarded."}


@router.put("/users/{user_id}")
def update_user(user_id: str, u: UserUpdate, background_tasks: BackgroundTasks, 
                current_user: dict = Depends(require_admin), cursor = Depends(get_db_cursor)):
    
    if u.role == 'read_only':
        u.base_capacity = 0.0

    ew = u.end_week if str(u.end_week).strip() != '' else None
    ey = u.end_year if str(u.end_year).strip() != '' else None
    
    cursor.execute(
        '''UPDATE users 
           SET name=%s, role=%s, location=%s, base_capacity=%s, 
               start_week=%s, start_year=%s, end_week=%s, end_year=%s 
           WHERE id=%s''',
        (u.name, u.role, u.location, u.base_capacity, u.start_week, u.start_year, ew, ey, user_id)
    )
    cursor.connection.commit()
    background_tasks.add_task(manager.broadcast, '{"action": "REFRESH_BOARD"}')

    background_tasks.add_task(
        log_audit_event,
        user_id=current_user["id"],
        username=current_user["username"],
        action="UPDATE_USER",
        resource_type="USER",
        resource_id=user_id,
        details="Updated user lifecycle metadata."
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