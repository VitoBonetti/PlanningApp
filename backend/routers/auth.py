from fastapi import APIRouter, HTTPException, Depends, status, Request, BackgroundTasks
import os
import uuid
from database import get_db_cursor
from audit_logger import log_audit_event
from websockets_manager import manager
from slowapi import Limiter
from slowapi.util import get_remote_address
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

router = APIRouter(tags=["Authentication"])
limiter = Limiter(key_func=get_remote_address)

MASTER_ADMIN_EMAIL = os.environ.get("MASTER_ADMIN_EMAIL")
IAP_AUDIENCE = os.environ.get("IAP_AUDIENCE")


def verify_iap_jwt(jwt_token: str) -> str:
    """Cryptographically verifies the Google IAP JWT and extracts the email."""
    try:
        decoded_jwt = id_token.verify_token(
            jwt_token,
            google_requests.Request(),
            audience=IAP_AUDIENCE,
            certs_url='https://www.gstatic.com/iap/verify/public_key'
        )
        return decoded_jwt['email'].lower()
    except Exception as e:
        print(f"🚨 IAP JWT Verification Failed: {e}")
        raise ValueError("Invalid IAP JWT Signature")


def get_current_user(request: Request, cursor=Depends(get_db_cursor)):
    # 1. Read the cryptographic JWT header instead of the plain-text one
    iap_jwt = request.headers.get("x-goog-iap-jwt-assertion")

    if not iap_jwt:
        if os.environ.get("ENV") == "local":
            email = MASTER_ADMIN_EMAIL.lower()
        else:
            # If we are in production and there is no IAP JWT, KILL the request.
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unauthorized: Missing Google IAP JWT. Direct access is forbidden."
            )
    else:
        try:
            # 2. Cryptographically verify the token
            email = verify_iap_jwt(iap_jwt)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=str(e)
            )

    # 3. Check if the user exists in your database
    cursor.execute("SELECT id, username, name, role, location FROM users WHERE username = %s", (email,))
    user = cursor.fetchone()

    # 4. ZERO-TOUCH SETUP: Auto-create the user if they don't exist
    if not user:
        is_master = (email == MASTER_ADMIN_EMAIL.lower())
        role = "admin" if is_master else "pentester"
        name = "Master Admin" if is_master else email.split("@")[0].replace(".", " ").title()

        new_id = str(uuid.uuid4())

        cursor.execute("""
            INSERT INTO users (id, username, name, role, location, base_capacity, start_week)
            VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id, username, name, role, location
        """, (new_id, email, name, role, "HQ", 1.0, 1))

        user = cursor.fetchone()
        cursor.connection.commit()

        log_audit_event(
            user_id=user[0], username=user[1], action="USER_AUTO_CREATED",
            resource_type="SYSTEM", details=f"Auto-provisioned {role} account via Google IAP."
        )

    return {"id": user[0], "username": user[1], "name": user[2], "role": user[3], "location": user[4]}


def require_admin(current_user: dict = Depends(get_current_user)):
    """Strictly locks an endpoint to Admins only."""
    if current_user.get('role') != 'admin':
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges required.")
    return current_user


def require_write_access(current_user: dict = Depends(get_current_user)):
    """Allows Admins and Pentesters, blocks Read-Only."""
    if current_user.get('role') == 'read_only':
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Read-only account cannot perform this action.")
    return current_user


@router.post("/logout")
def logout(background_tasks: BackgroundTasks, current_user: dict = Depends(get_current_user)):
    """
    With IAP, we don't need to clear JWT cookies. 
    We just use this to trigger the Websocket departure and Audit Log.
    """
    background_tasks.add_task(
        manager.broadcast,
        f'{{"action": "USER_LEFT", "username": "{current_user["username"]}"}}'
    )

    background_tasks.add_task(
        log_audit_event,
        user_id=current_user["id"],
        username=current_user["username"],
        action="LOGOUT",
        resource_type="SESSION",
        details="User logged out of application."
    )
    
    return {"message": "Successfully logged out"}
