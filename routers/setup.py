from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import secrets
import bcrypt
import psycopg2
from secrets_manager import get_system_config, save_system_config
from database import init_db

router = APIRouter(tags=["System Setup"])


class SetupPayload(BaseModel):
    db_host: str
    db_port: str
    db_user: str
    db_pass: str
    db_name: str
    admin_username: str
    admin_password: str
    admin_name: str


@router.get("/system/status")
def get_system_status():
    """The React app calls this on boot to see if it should show the Setup Wizard."""
    config = get_system_config()
    return {"setup_required": config is None}


@router.post("/system/setup")
def execute_system_setup(payload: SetupPayload):
    # 1. Prevent running setup twice
    if get_system_config() is not None:
        raise HTTPException(status_code=400, detail="System is already configured.")

    # 2. Test the PostgreSQL Database Connection FIRST
    try:
        conn = psycopg2.connect(
            host=payload.db_host, port=payload.db_port,
            user=payload.db_user, password=payload.db_pass, dbname=payload.db_name
        )
        conn.close()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Database connection failed: {e}")

    # 3. Generate a massive 256-bit cryptographically secure JWT Secret
    new_jwt_secret = secrets.token_hex(32)

    # 4. Bundle everything and push to GCP Secret Manager!
    master_config = {
        "jwt_secret": new_jwt_secret,
        "db_host": payload.db_host,
        "db_port": payload.db_port,
        "db_user": payload.db_user,
        "db_pass": payload.db_pass,
        "db_name": payload.db_name
    }

    # Save it to GCP (this will wait until it succeeds)
    save_system_config(master_config)

    # 5. Build the Database Tables
    try:
        init_db()
    except Exception as e:
        print(f"Error initializing DB: {e}")

    # 6. Insert the First Admin User
    salt = bcrypt.gensalt()
    hashed_pw = bcrypt.hashpw(payload.admin_password.encode('utf-8'), salt).decode('utf-8')
    admin_id = secrets.token_hex(8)

    conn = psycopg2.connect(**{k.replace('db_', ''): v for k, v in master_config.items() if k.startswith('db_')})
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO users (id, username, hashed_password, role, name, location, base_capacity) VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (admin_id, payload.admin_username, hashed_pw, 'admin', payload.admin_name, 'Global', 1.0)
    )
    conn.commit()
    conn.close()

    return {"message": "System successfully initialized! You may now log in."}