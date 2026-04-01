import uuid
from google.cloud.sql.connector import Connector, IPTypes
import os
from secrets_manager import get_system_config
from fastapi import HTTPException
from contextlib import contextmanager


connector = Connector()
PROJECT_ID = os.environ.get("GCP_PROJECT_ID")
LOCATION = os.environ.get("LOCATION")
INSTANCE_NAME = os.environ.get("DB_INSTANCE_NAME")
DB_NAME = os.environ.get("POSTGRES_DB")
DB_USER = os.environ.get("IAM_SA_EMAIL")


def get_db_connection():
    """
    Creates a passwordless connection to Cloud SQL using IAM.
    The Connector automatically requests and refreshes the OAuth token.
    """
    instance_connection_name = f"{PROJECT_ID}:{LOCATION}:{INSTANCE_NAME}"
    config = get_system_config()

    try:
        conn = connector.connect(
            instance_connection_name,
            "pg8000",
            user=DB_USER,
            db=DB_NAME,
            enable_iam_auth=True,  # This tells the connector to use the IAM token!
            ip_type=IPTypes.PRIVATE  # We are using the Private IP VPC bridge!
        )
        return conn
    except Exception as e:
        print(f"🚨 Failed to connect to Cloud SQL: {e}")
        return None


def get_db_cursor():
    """Safely yields a database cursor and ensures connection closure."""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=503, detail="Database connection unavailable.")

    try:
        cursor = conn.cursor()
        yield cursor  # The route uses the cursor here!
        conn.commit()  # Auto-commit if no errors happened
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()
        conn.close()


@contextmanager
def db_cursor_context():
    """A standard Python context manager for WebSockets or background tasks."""
    conn = get_db_connection()
    if not conn:
        yield None
        return

    try:
        cursor = conn.cursor()
        yield cursor
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()
        conn.close()


def init_db():
    """
    Ensures the schema exists. 
    Obsolete auth columns (TOTP, tokens) are no longer managed here.
    """
    conn = get_db_connection()
    if conn is None:
        return

    c = conn.cursor()

    # Core Tables
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        username TEXT UNIQUE,
        hashed_password TEXT,
        name TEXT,
        role TEXT,
        location TEXT,
        base_capacity REAL,
        start_week INTEGER DEFAULT 1,
        session_token TEXT DEFAULT '' 
    )''')
   

    c.execute('''CREATE TABLE IF NOT EXISTS services (
            id TEXT PRIMARY KEY,
            name TEXT,
            max_concurrent_per_week INTEGER
        )''')

        # 3. Tests Table
    c.execute('''CREATE TABLE IF NOT EXISTS tests (
        id TEXT PRIMARY KEY,
        name TEXT,
        service_id TEXT,
        type TEXT,
        credits_per_week REAL,
        duration_weeks REAL,
        start_week INTEGER,
        start_year INTEGER,
        status TEXT DEFAULT 'Not Planned',
        whitebox_category TEXT DEFAULT ''
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS events (
        id TEXT PRIMARY KEY,
        user_id TEXT,
        event_type TEXT,
        location TEXT,
        start_date TEXT,
        end_date TEXT
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS assignments (
        id TEXT PRIMARY KEY,
        test_id TEXT,
        user_id TEXT,
        week_number INTEGER,
        year INTEGER,
        allocated_credits REAL
    )''')
   
    c.execute('''CREATE TABLE IF NOT EXISTS assets (
        id TEXT PRIMARY KEY,
        inventory_id TEXT,
        ext_id TEXT,
        number TEXT,
        name TEXT,
        market TEXT,
        gost_service TEXT,
        is_assigned BOOLEAN DEFAULT FALSE,
        business_critical TEXT DEFAULT '',
        kpi TEXT DEFAULT '',
        whitebox_category TEXT DEFAULT '',
        UNIQUE (inventory_id, ext_id, number)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS test_assets (
        test_id TEXT REFERENCES tests(id),
        asset_id TEXT REFERENCES assets(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS notifications (
        id TEXT PRIMARY KEY,
        user_id TEXT,
        message TEXT,
        type TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        is_read BOOLEAN DEFAULT FALSE
    )''')

    c.execute("SELECT COUNT(*) FROM services")
    if c.fetchone()[0] == 0:
        c.executemany("INSERT INTO services (id, name, max_concurrent_per_week) VALUES (%s, %s, %s)", [
            (str(uuid.uuid4()), 'Adversary Simulation', 2),
            (str(uuid.uuid4()), 'White Box', 5),
            (str(uuid.uuid4()), 'Projects', 10),
            (str(uuid.uuid4()), 'Black Box', 20)
        ])

    conn.commit()
    conn.close()
