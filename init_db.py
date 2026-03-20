import sqlite3
import os
import bcrypt

DB_FILE = 'pentest_planner.db'

def reset_database():
    # 1. Easy Reset: Delete the file if it exists
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)
        print("Old database deleted.")

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # 2. Users Table (Now with explicit roles for permissions)
    cursor.execute('''
    CREATE TABLE users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        hashed_password TEXT NOT NULL,
        name TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('admin', 'manager', 'pentester')),
        location TEXT NOT NULL DEFAULT 'Global',
        base_capacity REAL DEFAULT 1.0
    )
    ''')

    # 3. Services/Categories (Based on your drawing's left column)
    cursor.execute('''
    CREATE TABLE services (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        max_concurrent_per_week INTEGER NOT NULL
    )
    ''')

    # 4. Events (Holidays & Side Projects)
    cursor.execute('''
    CREATE TABLE events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER, 
        event_type TEXT NOT NULL CHECK(event_type IN ('personal_holiday', 'national_holiday', 'side_project')),
        location TEXT, -- NEW: Which country does this national holiday apply to?
        start_date TEXT NOT NULL,
        end_date TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
    ''')

    # 5. Tests & Projects (Updated for durations and required credits)
    cursor.execute('''
    CREATE TABLE tests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        service_id INTEGER NOT NULL,
        type TEXT NOT NULL CHECK(type IN ('test', 'project')),
        credits_per_week REAL NOT NULL,
        duration_weeks INTEGER NOT NULL DEFAULT 1,
        start_week INTEGER,  -- NEW: Null means it's in the backlog
        start_year INTEGER,  -- NEW: The year it's scheduled
        FOREIGN KEY (service_id) REFERENCES services(id)
    )
    ''')

    # 6. Assignments (Mapping a user to a specific test for a specific week)
    cursor.execute('''
    CREATE TABLE assignments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        test_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        week_number INTEGER NOT NULL,
        year INTEGER NOT NULL,
        allocated_credits REAL NOT NULL,
        FOREIGN KEY (test_id) REFERENCES tests(id),
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
    ''')

    # --- SEED SECURE DATA ---
    # NEW: Generate a secure salt and hash the password natively using bcrypt
    salt = bcrypt.gensalt()
    default_pw = bcrypt.hashpw("ppwqqbkmhkpdegmnbrvfmkvpj".encode('utf-8'), salt).decode('utf-8')
    cursor.execute(
        "INSERT INTO users (username, hashed_password, name, role, location) VALUES ('admin', ?, 'System Admin', 'admin', 'Global')",
        (default_pw,))

    # Seed Services
    cursor.execute("INSERT INTO services (name, max_concurrent_per_week) VALUES ('Adversary Simulation', 2)")
    cursor.execute("INSERT INTO services (name, max_concurrent_per_week) VALUES ('White Box', 4)")
    cursor.execute("INSERT INTO services (name, max_concurrent_per_week) VALUES ('Projects', 3)")

    conn.commit()
    conn.close()
    print("Secure database created with Usernames and natively Hashed Passwords!")

if __name__ == '__main__':
    reset_database()