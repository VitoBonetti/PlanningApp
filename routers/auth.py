from fastapi import APIRouter, HTTPException, Depends, status, Response, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
import sqlite3
import jwt
from datetime import datetime, timedelta, timezone
import bcrypt
import os
from google.cloud import secretmanager
from database import DB_FILE
from slowapi import Limiter
from slowapi.util import get_remote_address
import uuid

router = APIRouter(tags=["Authentication"])
limiter = Limiter(key_func=get_remote_address)

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 120
PROJECT_ID = "planningapp-491007"


def get_secret(secret_id, project_id):
    # Fallback ONLY for local development
    if os.environ.get("ENV") == "local":
        return "local-dev-secret-key"

    try:
        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
        response = client.access_secret_version(request={"name": name})
        return response.payload.data.decode("UTF-8")
    except Exception as e:
        print(f"CRITICAL: Failed to fetch secret: {e}")
        # FAIL SECURE: Crash the app instead of using an insecure key in production!
        raise RuntimeError(f"Cannot start application without {secret_id}. Check GCP permissions.")


SECRET_KEY = get_secret("JWT_SECRET_KEY", PROJECT_ID)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def verify_password(plain_password, hashed_password):
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))


def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


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

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, name, role, location, session_token FROM users WHERE username = ?", (username,))
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
def login_for_access_token(request: Request, response: Response, form_data: OAuth2PasswordRequestForm = Depends()):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, hashed_password, role, name, location FROM users WHERE username = ?", (form_data.username,))
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
    return {"id": user[0], "role": user[3], "name": user[4], "location": user[5]}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie("access_token")
    return {"message": "Logged out"}
