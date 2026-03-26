from fastapi import APIRouter, HTTPException, Depends, status, Response, Request, BackgroundTasks
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
import jwt
from datetime import datetime, timedelta, timezone
import bcrypt
from secrets_manager import get_system_config
from database import get_db_connection
from slowapi import Limiter
from slowapi.util import get_remote_address
import uuid
from audit_logger import log_audit_event

router = APIRouter(tags=["Authentication"])
limiter = Limiter(key_func=get_remote_address)

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 120


config = get_system_config()
SECRET_KEY = config.get("jwt_secret") if config else "temporary-setup-mode-key"
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


def verify_password(plain_password, hashed_password):
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))


def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def get_current_user(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        session_token: str = payload.get("session")
        if username is None or session_token is None: 
            raise HTTPException(status_code=401, detail="Invalid token structure")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, name, role, location, session_token FROM users WHERE username = %s", (username,))
    user = cursor.fetchone()
    conn.close()

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
def login_for_access_token(request: Request, response: Response, background_tasks: BackgroundTasks, form_data: OAuth2PasswordRequestForm = Depends()):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, hashed_password, role, name, location FROM users WHERE username = %s", (form_data.username,))
    user = cursor.fetchone()
    if not user or not verify_password(form_data.password, user[2]):
        conn.close()
        raise HTTPException(status_code=401, detail="Incorrect username or password")

    if not user or not verify_password(form_data.password, user[2]):
        raise HTTPException(status_code=401, detail="Incorrect username or password")

    new_session = str(uuid.uuid4())
    cursor.execute("UPDATE users SET session_token = ? WHERE id = ?", (new_session, user[0]))
    conn.commit()
    conn.close()

    access_token = create_access_token(data={"sub": user[1], "session": new_session})

    # Issue HttpOnly Cookie!
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )

    background_tasks.add_task(
        log_audit_event,
        user_id=user[0],
        username=user[1],
        action="LOGIN",
        resource_type="SESSION",
        details="User successfully authenticated."
    )

    return {"id": user[0], "role": user[3], "name": user[4], "location": user[5]}


@router.post("/logout")
def logout(response: Response, background_tasks: BackgroundTasks, current_user: dict = Depends(get_current_user)):
    response.delete_cookie("access_token")
    background_tasks.add_task(
        log_audit_event,
        user_id=current_user["id"],
        username=current_user["username"],
        action="LOGOUT",
        resource_type="SESSION"
    )
    return {"message": "Successfully logged out"}
