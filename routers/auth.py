from fastapi import APIRouter, HTTPException, Depends, status, Response, Request, BackgroundTasks
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
import jwt
from datetime import datetime, timedelta, timezone
import bcrypt
from secrets_manager import get_system_config
from database import get_db_cursor
from slowapi import Limiter
from slowapi.util import get_remote_address
import uuid
from audit_logger import log_audit_event
import secrets
from websockets_manager import manager

router = APIRouter(tags=["Authentication"])
limiter = Limiter(key_func=get_remote_address)

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 5
REFRESH_TOKEN_EXPIRE_DAYS = 7


# config = get_system_config()
# SECRET_KEY = config.get("jwt_secret") if config else secrets.token_urlsafe(32)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
_cached_secret_key = None


def get_jwt_secret():
    global _cached_secret_key
    if _cached_secret_key:
        return _cached_secret_key
    
    config = get_system_config()
    if config and "jwt_secret" in config:
        _cached_secret_key = config["jwt_secret"]
        return _cached_secret_key
    
    # Do NOT cache the fallback, so it checks again after setup finishes
    return secrets.token_urlsafe(32)


def verify_password(plain_password, hashed_password):
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))


def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    # encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    encoded_jwt = jwt.encode(to_encode, get_jwt_secret(), algorithm=ALGORITHM)
    return encoded_jwt


def get_current_user(request: Request, cursor = Depends(get_db_cursor)):
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    try:
        # payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        session_token: str = payload.get("session")
        if username is None or session_token is None: 
            raise HTTPException(status_code=401, detail="Invalid token structure")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    cursor.execute("SELECT id, username, name, role, location, session_token FROM users WHERE username = %s", (username,))
    user = cursor.fetchone()

    if user is None or user[5] != session_token: 
        raise HTTPException(status_code=401, detail="Session expired or logged in elsewhere.")
        
    return {"id": user[0], "username": user[1], "name": user[2], "role": user[3], "location": user[4]}


def require_admin(current_user: dict = Depends(get_current_user)):
    """Strictly locks an endpoint to Admins only."""
    if current_user.get('role') != 'admin':
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges required.")
    return current_user


def require_write_access(current_user: dict = Depends(get_current_user)):
    """Allows Admins and Pentesters (e.g., to book their own holidays), blocks Read-Only."""
    if current_user.get('role') == 'read_only':
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Read-only account cannot perform this action.")
    return current_user


@router.post("/token")
@limiter.limit("5/minute")
def login_for_access_token(request: Request, response: Response, background_tasks: BackgroundTasks, form_data: OAuth2PasswordRequestForm = Depends(), cursor = Depends(get_db_cursor)):

    cursor.execute("SELECT id, username, hashed_password, role, name, location FROM users WHERE username = %s", (form_data.username,))
    user = cursor.fetchone()

    if not user or not verify_password(form_data.password, user[2]):
        raise HTTPException(status_code=401, detail="Incorrect username or password")

    # generate Tokens
    new_session = str(uuid.uuid4())
    access_token = create_access_token(data={"sub": user[1], "session": new_session})

    # Generate the raw token and hash it
    raw_refresh_secret = secrets.token_urlsafe(32)
    salt = bcrypt.gensalt()
    hashed_refresh = bcrypt.hashpw(raw_refresh_secret.encode('utf-8'), salt).decode('utf-8')

    refresh_cookie_value = f"{user[0]}:{raw_refresh_secret}"
    
    cursor.execute(
        "UPDATE users SET session_token = %s, refresh_token = %s WHERE id = %s",
        (new_session, hashed_refresh, user[0])
    )
    cursor.connection.commit()

    response.set_cookie(key="access_token", value=access_token, httponly=True, secure=True, samesite="lax",
                        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60)
    response.set_cookie(key="refresh_token", value=refresh_cookie_value, httponly=True, secure=True, samesite="lax",
                        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60, path="/api/auth/refresh")

    background_tasks.add_task(log_audit_event, user_id=user[0], username=user[1], action="LOGIN",
                              resource_type="SESSION", details="User successfully authenticated.")

    background_tasks.add_task(
        log_audit_event,
        user_id=user[0],
        username=user[1],
        action="LOGIN",
        resource_type="SESSION",
        details="User successfully authenticated."
    )

    return {"id": user[0], "role": user[3], "name": user[4], "location": user[5]}


@router.post("/auth/refresh")
@limiter.limit("5/minute")
def refresh_access_token(request: Request, response: Response, cursor = Depends(get_db_cursor)):
    old_refresh_cookie = request.cookies.get("refresh_token")
    if not old_refresh_cookie or ":" not in old_refresh_cookie:
        raise HTTPException(status_code=401, detail="Invalid refresh token format")

    # Find the user by this refresh token
    try:
        user_id, raw_refresh_secret = old_refresh_cookie.split(":", 1)
    except ValueError:
        raise HTTPException(status_code=401, detail="Malformed refresh token")

    cursor.execute("SELECT id, username, refresh_token FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()

    if not user or not user[2] or not bcrypt.checkpw(raw_refresh_secret.encode('utf-8'), user[2].encode('utf-8')):
        # SECURITY ALERT: If it fails, they are using a bad/old token.
        # Force a total logout for safety.
        if user:
            cursor.execute("UPDATE users SET session_token = NULL, refresh_token = NULL WHERE id = %s", (user[0],))
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    # ROTATION: Generate brand new tokens
    new_session_id = str(uuid.uuid4())
    new_access_token = create_access_token(data={"sub": user[1], "session": new_session_id})

    new_raw_secret = secrets.token_urlsafe(32)
    new_hashed_refresh = bcrypt.hashpw(new_raw_secret.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    new_refresh_cookie_value = f"{user[0]}:{new_raw_secret}"

    cursor.execute(
        "UPDATE users SET session_token = %s, refresh_token = %s WHERE id = %s",
        (new_session_id, new_hashed_refresh, user[0])
    )
    cursor.connection.commit()
    
    response.set_cookie(key="access_token", value=new_access_token, httponly=True, secure=True, samesite="lax")
    response.set_cookie(key="refresh_token", value=new_refresh_cookie_value, httponly=True, secure=True, samesite="lax",
                        path="/api/auth/refresh")

    return {"status": "refreshed"}


@router.post("/logout")
def logout(response: Response, background_tasks: BackgroundTasks, current_user: dict = Depends(get_current_user), cursor = Depends(get_db_cursor)):
    # Clear the session token in the database
    cursor.execute("UPDATE users SET session_token = NULL, refresh_token = NULL WHERE id = %s", (current_user["id"],))
    cursor.connection.commit()
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")

    background_tasks.add_task(
        manager.broadcast,
        f'{{"action": "USER_LEFT", "username": "{current_user["username"]}"}}'
    )

    background_tasks.add_task(
        log_audit_event,
        user_id=current_user["id"],
        username=current_user["username"],
        action="LOGOUT",
        resource_type="SESSION"
    )
    return {"message": "Successfully logged out"}
