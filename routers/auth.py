from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
import sqlite3
import jwt
from datetime import datetime, timedelta, timezone
import bcrypt
import os
from google.cloud import secretmanager
from database import DB_FILE

router = APIRouter(tags=["Authentication"])

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 120
PROJECT_ID = "planningapp-491007"


def get_secret(secret_id, project_id):
    # Fallback for local development so your app doesn't crash on your laptop
    if os.environ.get("ENV") == "local":
        return "local-dev-secret-key"

    try:
        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
        response = client.access_secret_version(request={"name": name})
        return response.payload.data.decode("UTF-8")
    except Exception as e:
        print(f"Failed to fetch secret: {e}")
        # Failsafe so the app still boots if GCP acts up, but warns you
        return "fallback-insecure-key"


SECRET_KEY = get_secret("JWT_SECRET_KEY", PROJECT_ID)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def verify_password(plain_password, hashed_password):
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))


def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                          detail="Could not validate credentials",
                                          headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None: raise credentials_exception
    except jwt.InvalidTokenError:
        raise credentials_exception

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, name, role, location FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    conn.close()

    if user is None: raise credentials_exception
    return {"id": user[0], "username": user[1], "name": user[2], "role": user[3], "location": user[4]}


@router.post("/token")
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, hashed_password, role, name FROM users WHERE username = ?",
                   (form_data.username,))
    user = cursor.fetchone()
    conn.close()

    if not user or not verify_password(form_data.password, user[2]):
        raise HTTPException(status_code=401, detail="Incorrect username or password")

    access_token = create_access_token(data={"sub": user[1]})
    return {"access_token": access_token, "token_type": "bearer", "role": user[3], "name": user[4]}