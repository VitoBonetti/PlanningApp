import uuid
import sqlite3

DB_FILE = '/app/data/planner_v2.db'

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    # Core Tables
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (
                     id  TEXT  PRIMARY KEY,
                     username TEXT UNIQUE,
                     hashed_password TEXT,
                     name TEXT,
                     role TEXT,
                     location TEXT,
                     base_capacity REAL,
                     start_week INTEGER DEFAULT 1
                 )''')

    c.execute('''CREATE TABLE IF NOT EXISTS services
                 (
                     id TEXT PRIMARY KEY,
                     name TEXT,
                     max_concurrent_per_week INTEGER
                 )''')

    c.execute('''CREATE TABLE IF NOT EXISTS tests
                 (
                     id TEXT PRIMARY KEY,
                     name TEXT,
                     service_id TEXT,
                     type TEXT,
                     credits_per_week REAL,
                     duration_weeks REAL,
                     start_week INTEGER,
                     start_year INTEGER,
                     status TEXT DEFAULT 'Not Planned'
                 )''')

    try:
        c.execute("ALTER TABLE tests ADD COLUMN whitebox_category TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass

    c.execute('''CREATE TABLE IF NOT EXISTS events
                 (
                     id TEXT PRIMARY KEY,
                     user_id TEXT,
                     event_type TEXT,
                     location TEXT,
                     start_date TEXT,
                     end_date TEXT
                 )''')

    c.execute('''CREATE TABLE IF NOT EXISTS assignments
                 (
                     id TEXT PRIMARY KEY,
                     test_id TEXT,
                     user_id TEXT,
                     week_number INTEGER,
                     year INTEGER,
                     allocated_credits REAL
                 )''')

    # Asset Tables
    c.execute('''CREATE TABLE IF NOT EXISTS assets 
    (
        id TEXT PRIMARY KEY,
        inventory_id TEXT,
        ext_id TEXT,
        number TEXT,
        name TEXT,
        market TEXT,
        gost_service TEXT,
        is_assigned BOOLEAN DEFAULT 0,
        business_critical TEXT,
        kpi TEXT,
        whitebox_category TEXT
        is_assigned BOOLEAN DEFAULT 0,
        UNIQUE ( inventory_id, ext_id, number )
        )
    ''')

    # Safe Migrations: Add columns to existing databases without wiping data
    try: c.execute("ALTER TABLE assets ADD COLUMN business_critical TEXT DEFAULT ''")
    except sqlite3.OperationalError: pass

    try: c.execute("ALTER TABLE assets ADD COLUMN kpi TEXT DEFAULT ''")
    except sqlite3.OperationalError: pass

    try: c.execute("ALTER TABLE assets ADD COLUMN whitebox_category TEXT DEFAULT ''")
    except sqlite3.OperationalError: pass

    c.execute('''CREATE TABLE IF NOT EXISTS test_assets
    (
        test_id
        TEXT,
        asset_id
        TEXT,
        FOREIGN
        KEY
                 (
        test_id
                 ) REFERENCES tests
                 (
                     id
                 ), FOREIGN KEY
                 (
                     asset_id
                 ) REFERENCES assets
                 (
                     id
                 ))''')

    # Seed Default Service Lanes if the board is completely empty
    c.execute("SELECT COUNT(*) FROM services")
    if c.fetchone()[0] == 0:
        c.executemany("INSERT INTO services (id, name, max_concurrent_per_week) VALUES (?, ?, ?)", [
            (str(uuid.uuid4()), 'Adversary Simulation', 2),
            (str(uuid.uuid4()), 'White Box', 5),
            (str(uuid.uuid4()), 'Projects', 10),
            (str(uuid.uuid4()), 'Black Box', 20)
        ])

    conn.commit()
    conn.close()

init_db()
