from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import secrets
import bcrypt
import psycopg2
from secrets_manager import get_system_config, save_system_config
from database import init_db
import os

router = APIRouter(tags=["System Setup"])


class SetupPayload(BaseModel):
    use_custom_db: bool
    db_host: str | None = None
    db_port: str | None = None
    db_user: str | None = None
    db_pass: str | None = None
    db_name: str | None = None
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

    # 2. Decide which credentials to use!
    if payload.use_custom_db:
        final_db_host = payload.db_host
        final_db_port = payload.db_port
        final_db_user = payload.db_user
        final_db_pass = payload.db_pass
        final_db_name = payload.db_name
    else:
        # User chose default. Read the SETUP variables from docker-compose!
        final_db_host = os.environ.get("SETUP_DB_HOST")
        final_db_port = os.environ.get("SETUP_DB_PORT")
        final_db_user = os.environ.get("SETUP_DB_USER")
        final_db_pass = os.environ.get("SETUP_DB_PASS")
        final_db_name = os.environ.get("SETUP_DB_NAME")

        if not final_db_pass:
            raise HTTPException(status_code=500, detail="Backend is missing default .env configuration.")

    # 3. Test the PostgreSQL Database Connection FIRST
    try:
        conn = psycopg2.connect(
            host=final_db_host, port=final_db_port,
            user=final_db_user, password=final_db_pass, dbname=final_db_name
        )
        conn.close()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Database connection failed: {e}")

    # 4. Generate a massive 256-bit cryptographically secure JWT Secret
    new_jwt_secret = secrets.token_hex(32)

    # 5. Bundle everything and push to GCP Secret Manager!
    master_config = {
        "jwt_secret": new_jwt_secret,
        "db_host": final_db_host,
        "db_port": final_db_port,
        "db_user": final_db_user,
        "db_pass": final_db_pass,
        "db_name": final_db_name
    }

    # Save it to GCP (this will wait until it succeeds)
    save_system_config(master_config)

    # 6. Build the Database Tables
    try:
        init_db()
    except Exception as e:
        print(f"Error initializing DB: {e}")

    # 7. Insert the First Admin User
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