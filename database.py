import uuid
from google.cloud.sql.connector import Connector, IPTypes
import os
from fastapi import HTTPException
from contextlib import contextmanager
from sqlalchemy.pool import QueuePool


connector = Connector()
PROJECT_ID = os.environ.get("GCP_PROJECT_ID")
LOCATION = os.environ.get("LOCATION")
INSTANCE_NAME = os.environ.get("DB_INSTANCE_NAME")
DB_NAME = os.environ.get("POSTGRES_DB")
DB_USER = os.environ.get("IAM_SA_EMAIL")

instance_connection_name = f"{PROJECT_ID}:{LOCATION}:{INSTANCE_NAME}"

def getconn():
    """This does the heavy cryptographic handshake."""
    return connector.connect(
        instance_connection_name,
        "pg8000",
        user=DB_USER,
        db=DB_NAME,
        enable_iam_auth=True,
        ip_type=IPTypes.PRIVATE
    )

# This keeps 10 connections permanently open and ready instantly.
# If more are needed during a spike, it can overflow up to 20.
pool = QueuePool(getconn, pool_size=10, max_overflow=20, timeout=30)

def get_db_connection():
    try:
        return pool.connect()
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

    c.execute('''CREATE TABLE IF NOT EXISTS test_history (
        id TEXT PRIMARY KEY,
        test_id TEXT REFERENCES tests(id) ON DELETE CASCADE,
        action TEXT,
        week_number INTEGER,
        year INTEGER,
        changed_by_user_id TEXT,
        changed_by_username TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS raw_assets (
        inventory_id TEXT,
        legacy_id INTEGER,
        name TEXT,
        managing_organization TEXT,
        hosting_location TEXT,
        type TEXT,
        status TEXT,
        stage TEXT,
        business_critical INTEGER,
        confidentiality_rating INTEGER,
        integrity_rating INTEGER,
        availability_rating INTEGER,
        internet_facing TEXT,
        iaas_paas_saas TEXT,
        master_record TEXT,
        number TEXT,
        stage_ritm TEXT,
        short_description TEXT,
        requested_for TEXT,
        opened_by TEXT,
        company TEXT,
        created TIMESTAMP,
        name_of_application TEXT,
        url_of_application TEXT,
        estimated_date_pentest DATE,
        opened TIMESTAMP,
        state TEXT,
        assignment_group TEXT,
        assigned_to TEXT,
        closed TIMESTAMP,
        closed_by TEXT,
        close_notes TEXT,
        service_type TEXT,
        market TEXT,
        kpi BOOLEAN,
        date_first_seen DATE,
        pentest_queue BOOLEAN,
        gost_service TEXT,
        whitebox_category TEXT,
        quarter_planned TEXT,
        year_planned TEXT,
        planned_with_ritm BOOLEAN,
        month_planned TEXT,
        week_planned TEXT,
        tested_2024_ritm TEXT,
        tested_2025_ritm TEXT,
        prevision_2027 TEXT,
        confirmed_by_market BOOLEAN,
        status_manual_tracking TEXT,
        last_synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (inventory_id, legacy_id, number)
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
