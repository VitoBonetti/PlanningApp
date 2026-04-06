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
    Native Migration Engine.
    Reads .sql files from the 'migrations' folder and applies them sequentially
    using the highly secure GCP IAM Connector.
    """
    conn = get_db_connection()
    if conn is None:
        return

    c = conn.cursor()

    try:
        #  Create a table to track which migrations have already run
        c.execute('''CREATE TABLE IF NOT EXISTS schema_migrations (
            id SERIAL PRIMARY KEY,
            filename TEXT UNIQUE,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        
        # Get the list of already applied migrations
        c.execute("SELECT filename FROM schema_migrations")
        applied_migrations = {row[0] for row in c.fetchall()}

        # Find our local migrations folder
        migrations_dir = os.path.join(os.path.dirname(__file__), 'migrations')
        if not os.path.exists(migrations_dir):
            os.makedirs(migrations_dir)

        # Sort the files alphabetically so 0001 runs before 0002
        files = sorted([f for f in os.listdir(migrations_dir) if f.endswith('.sql')])

        for filename in files:
            if filename not in applied_migrations:
                print(f"🔄 Applying migration: {filename}...")
                file_path = os.path.join(migrations_dir, filename)
                
                with open(file_path, 'r') as file:
                    sql_script = file.read()
                    
                    # pg8000 prefers executing commands one by one, so we split by semicolon
                    queries = [q.strip() for q in sql_script.split(';') if q.strip()]
                    
                    for query in queries:
                        c.execute(query)
                
                # Record that it finished successfully
                c.execute("INSERT INTO schema_migrations (filename) VALUES (%s)", (filename,))
                print(f"✅ Successfully applied: {filename}")

        # We can just leave this Python logic intact because it runs safely every time
        c.execute("SELECT COUNT(*) FROM services")
        if c.fetchone()[0] == 0:
            import uuid
            c.executemany("INSERT INTO services (id, name, max_concurrent_per_week) VALUES (%s, %s, %s)", [
                (str(uuid.uuid4()), 'Adversary Simulation', 2),
                (str(uuid.uuid4()), 'White Box', 5),
                (str(uuid.uuid4()), 'Projects', 10),
                (str(uuid.uuid4()), 'Black Box', 20)
            ])

        conn.commit()

    except Exception as e:
        conn.rollback()
        print(f"🚨 Migration Failed: {e}")
        raise e
    finally:
        c.close()
        conn.close()