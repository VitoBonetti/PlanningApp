import os
from sqlalchemy.pool import QueuePool
from google.cloud.sql.connector import Connector, IPTypes
from fastapi import HTTPException
from contextlib import contextmanager

connector = Connector()
PROJECT_ID = os.environ.get("GCP_PROJECT_ID")
LOCATION = os.environ.get("LOCATION")
INSTANCE_NAME = os.environ.get("DB_INSTANCE_NAME")
DB_NAME = os.environ.get("POSTGRES_DB")
DB_USER = os.environ.get("IAM_SA_EMAIL")
instance_connection_name = f"{PROJECT_ID}:{LOCATION}:{INSTANCE_NAME}"


def getconn():
    return connector.connect(
        instance_connection_name,
        "pg8000",
        user=DB_USER,
        db=DB_NAME,
        enable_iam_auth=True,
        ip_type=IPTypes.PRIVATE
    )


pool = QueuePool(getconn, pool_size=10, max_overflow=20, timeout=30)


def get_db_connection():
    try:
        return pool.connect()
    except Exception as e:
        print(f"🚨 Failed to connect to Cloud SQL: {e}")
        return None


def get_db_cursor():
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=503, detail="Database connection unavailable.")
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


@contextmanager
def db_cursor_context():
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


def run_alembic_migrations():
    """Triggered on Cloud Run boot"""
    conn = get_db_connection()
    if not conn:
        return
    c = conn.cursor()
    c.execute(
        "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'schema_migrations');")
    old_system_exists = c.fetchone()[0]
    c.execute(
        "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'alembic_version');")
    alembic_exists = c.fetchone()[0]
    c.close()
    conn.close()

    from alembic.config import Config
    from alembic import command

    alembic_cfg_path = os.path.join(os.path.dirname(__file__), "alembic.ini")
    alembic_cfg = Config(alembic_cfg_path)

    # If the old tables exist, tell Alembic to mark the baseline as "done" without executing it
    if old_system_exists and not alembic_exists:
        print("Stamping existing database...")
        command.stamp(alembic_cfg, "head")

    print("Running remaining Alembic migrations...")
    command.upgrade(alembic_cfg, "head")