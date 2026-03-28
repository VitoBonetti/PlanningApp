from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Request
import psycopg2
import uuid
import bcrypt
from database import get_db_connection
from routers.auth import get_current_user, verify_password, require_admin, limiter
from models import UserCreateSecure, UserUpdate, PasswordChange, AdminPasswordReset, FirstAdminSetup, UserSetupPassword
from websockets_manager import manager
from audit_logger import log_audit_event
import pyotp
from datetime import datetime, timedelta
import qrcode
import qrcode.image.svg
import base64
from io import BytesIO

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
def create_user(u: UserCreateSecure, request: Request, background_tasks: BackgroundTasks,
                current_user: dict = Depends(require_admin)):
    if u.role == 'read_only':
        u.base_capacity = 0.0

    new_id = str(uuid.uuid4())
    reset_token = str(uuid.uuid4())
    expires = datetime.now() + timedelta(hours=24)
    totp_secret = pyotp.random_base32()

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            '''INSERT INTO users (id, username, name, role, location, base_capacity, start_week, reset_token,
                                  reset_token_expires, is_totp_enabled, totp_secret)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, FALSE, %s)''',
            (new_id, u.username, u.name, u.role, u.location, u.base_capacity, u.start_week, reset_token, expires,
             totp_secret)
        )
        conn.commit()
        setup_link = f"{request.base_url}setup-account?token={reset_token}"
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
        return {
            "message": f"User {u.name} created.",
            "secure_link": setup_link,
            "instructions": "Copy this link and share it securely with the user. It expires in 24 hours."
        }
    except psycopg2.errors.UniqueViolation:
        if conn: conn.rollback()  # Always rollback on error
        raise HTTPException(status_code=400, detail="Username already exists.")
    finally:
        if conn: conn.close()


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
    reset_token = str(uuid.uuid4())
    expires = datetime.now() + timedelta(hours=2)  # Shorter expiry for resets

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET reset_token=%s, reset_token_expires=%s WHERE id=%s',
                   (reset_token, expires, user_id))
    conn.commit()
    conn.close()
    reset_link = f"{request.base_url}setup-account?token={reset_token}"
    background_tasks.add_task(
        log_audit_event,
        user_id=current_user["id"],
        username=current_user["username"],
        action="PSW_RESET",
        resource_type="USER",
        resource_id=user_id,
        details="REset link has been created."
    )
    return {
        "message": "Reset link generated.",
        "secure_link": reset_link,
        "instructions": "Share this link with the user. It expires in 2 hours."
    }


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


@router.post("/users/setup-password")
@limiter.limit("5/minute")
def setup_user_password(payload: UserSetupPassword, request: Request, background_tasks: BackgroundTasks):
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Find the user by the valid reset token
    cursor.execute(
        "SELECT id, username, totp_secret FROM users WHERE reset_token = %s AND reset_token_expires > %s",
        (payload.token, datetime.now())
    )
    user = cursor.fetchone()

    if not user:
        conn.close()
        raise HTTPException(status_code=400, detail="Invalid or expired setup link.")

    user_id, username, totp_secret = user[0], user[1], user[2]

    # 2. Verify the 2FA Code (Google Authenticator)
    totp = pyotp.TOTP(totp_secret)
    if not totp.verify(payload.totp_code):
        conn.close()
        raise HTTPException(status_code=401, detail="Invalid Authenticator code.")

    # 3. NOW we generate the salt and hash the new password
    salt = bcrypt.gensalt()
    hashed_pw = bcrypt.hashpw(payload.new_password.encode('utf-8'), salt).decode('utf-8')

    # 4. Save the secure hash, enable TOTP, and DESTROY the reset token
    cursor.execute(
        '''UPDATE users
           SET hashed_password     = %s,
               is_totp_enabled     = TRUE,
               reset_token         = NULL,
               reset_token_expires = NULL
           WHERE id = %s''',
        (hashed_pw, user_id)
    )
    conn.commit()
    conn.close()

    background_tasks.add_task(
        log_audit_event,
        user_id=user_id,
        username=username,
        action="ACCOUNT_SETUP",
        resource_type="USER",
        resource_id=user_id,
        details="User securely set their initial password and enabled 2FA."
    )

    return {"message": "Account secured. You may now log in."}

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


@router.get("/users/setup-info")
@limiter.limit("5/minute")
def get_user_setup_info(request: Request, token: str):
    """Fetches the username and generates the 2FA QR code for the setup screen."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT username, totp_secret FROM users WHERE reset_token = %s AND reset_token_expires > %s",
        (token, datetime.now())
    )
    user = cursor.fetchone()
    conn.close()

    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired setup link.")

    username, secret = user[0], user[1]

    # Generate SVG QR Code
    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(name=username, issuer_name="GOST ERP")
    factory = qrcode.image.svg.SvgImage
    qr = qrcode.make(uri, image_factory=factory)
    buffered = BytesIO()
    qr.save(buffered)
    qr_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")

    return {
        "username": username,
        "qr_code": f"data:image/svg+xml;base64,{qr_base64}"
    }

