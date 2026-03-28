from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
import secrets
import bcrypt
import psycopg2
import pyotp
import qrcode
import base64
from io import BytesIO
from secrets_manager import get_system_config, save_system_config
from database import init_db
import os
from audit_logger import fetch_recent_audit_logs


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
    totp_secret: str
    totp_code: str


@router.get("/system/status")
def get_system_status():
    """The React app calls this on boot to see if it should show the Setup Wizard."""
    config = get_system_config()
    return {"setup_required": config is None}

@router.get("/system/audit")
def get_audit_logs():
    """Returns the most recent system audit logs from BigQuery."""
    # Note: Because this is an admin view, you could add token dependency here later
    # to ensure only admins can fetch it!
    logs = fetch_recent_audit_logs()
    return logs


@router.get("/system/setup/totp")
def generate_setup_totp(request: Request):
    """Generates a provisional TOTP secret and QR code for the Day-0 admin."""
    if get_system_config() is not None:
        raise HTTPException(status_code=400, detail="System is already configured.")

    # 1. Generate a secure Base32 secret
    secret = pyotp.random_base32()

    # 2. Create the provisioning URI for Google Authenticator / Authy
    totp = pyotp.TOTP(secret)
    provisioning_uri = totp.provisioning_uri(name="Master Admin", issuer_name="GOST ERP")

    # 3. Generate the QR Code as a base64 image (so the frontend doesn't need extra libraries)
    factory = qrcode.image.svg.SvgImage
    qr = qrcode.make(provisioning_uri, image_factory=factory)
    buffered = BytesIO()
    qr.save(buffered)
    qr_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")

    return {
        "totp_secret": secret,
        "qr_code": f"data:image/svg+xml;base64,{qr_base64}"
    }


@router.post("/system/setup")
def execute_system_setup(payload: SetupPayload):
    # 1. Prevent running setup twice
    if get_system_config() is not None:
        raise HTTPException(status_code=400, detail="System is already configured.")

    totp = pyotp.TOTP(payload.totp_secret)
    if not totp.verify(payload.totp_code):
        raise HTTPException(status_code=401, detail="Invalid Authenticator Code. Please try again.")

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
            host=final_db_host,
            port=final_db_port,
            user=final_db_user,
            password=final_db_pass,
            dbname=final_db_name,
            sslmode="require"
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

    conn = psycopg2.connect(
        host=master_config["db_host"],
        port=master_config["db_port"],
        user=master_config["db_user"],
        password=master_config["db_pass"],
        dbname=master_config["db_name"],
        sslmode="require"
    )
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO users (id, username, hashed_password, role, name, location, base_capacity) VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (admin_id, payload.admin_username, hashed_pw, 'admin', payload.admin_name, 'Global', 1.0)
    )
    conn.commit()
    conn.close()

    return {"message": "System successfully initialized! You may now log in."}
