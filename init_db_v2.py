import sqlite3
import bcrypt
import uuid

DB_FILE = 'planner_v2.db'  # NEW DATABASE FILE!


def reset_database():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # ALL IDs ARE NOW TEXT (UUIDs)
    # Added 'read_only' to roles
    cursor.execute('''CREATE TABLE users
                      (
                          id              TEXT PRIMARY KEY,
                          username        TEXT UNIQUE NOT NULL,
                          hashed_password TEXT        NOT NULL,
                          name            TEXT        NOT NULL,
                          role            TEXT        NOT NULL CHECK (role IN ('admin', 'manager', 'pentester', 'read_only')),
                          location        TEXT        NOT NULL DEFAULT 'Global',
                          base_capacity   REAL                 DEFAULT 1.0
                      )''')
    cursor.execute('''CREATE TABLE services
                      (
                          id                      TEXT PRIMARY KEY,
                          name                    TEXT    NOT NULL,
                          max_concurrent_per_week INTEGER NOT NULL
                      )''')
    cursor.execute('''CREATE TABLE events
                      (
                          id         TEXT PRIMARY KEY,
                          user_id    TEXT,
                          event_type TEXT NOT NULL,
                          location   TEXT,
                          start_date TEXT NOT NULL,
                          end_date   TEXT NOT NULL,
                          FOREIGN KEY (user_id) REFERENCES users (id)
                      )''')

    # Added 'status' to tests
    cursor.execute('''CREATE TABLE tests
                      (
                          id               TEXT PRIMARY KEY,
                          name             TEXT    NOT NULL,
                          service_id       TEXT    NOT NULL,
                          type             TEXT    NOT NULL,
                          credits_per_week REAL    NOT NULL,
                          duration_weeks   INTEGER NOT NULL DEFAULT 1,
                          start_week       INTEGER,
                          start_year       INTEGER,
                          status           TEXT             DEFAULT 'Not Planned',
                          FOREIGN KEY (service_id) REFERENCES services (id)
                      )''')

    cursor.execute('''CREATE TABLE assignments
                      (
                          id                TEXT PRIMARY KEY,
                          test_id           TEXT    NOT NULL,
                          user_id           TEXT    NOT NULL,
                          week_number       INTEGER NOT NULL,
                          year              INTEGER NOT NULL,
                          allocated_credits REAL    NOT NULL,
                          FOREIGN KEY (test_id) REFERENCES tests (id),
                          FOREIGN KEY (user_id) REFERENCES users (id)
                      )''')

    # --- SEED V2 DATA ---
    salt = bcrypt.gensalt()
    default_pw = bcrypt.hashpw("ppwqqbkmhkpdegmnbrvfmkvpj".encode('utf-8'), salt).decode('utf-8')

    # Generate UUIDs for initial data
    admin_id = str(uuid.uuid4())
    cursor.execute(
        "INSERT INTO users (id, username, hashed_password, name, role, location) VALUES (?, 'admin', ?, 'System Admin', 'admin', 'Global')",
        (admin_id, default_pw))

    cursor.execute("INSERT INTO services (id, name, max_concurrent_per_week) VALUES (?, 'Adversary Simulation', 2)",
                   (str(uuid.uuid4()),))
    cursor.execute("INSERT INTO services (id, name, max_concurrent_per_week) VALUES (?, 'White Box', 4)",
                   (str(uuid.uuid4()),))
    cursor.execute("INSERT INTO services (id, name, max_concurrent_per_week) VALUES (?, 'Projects', 3)",
                   (str(uuid.uuid4()),))
    cursor.execute("INSERT INTO services (id, name, max_concurrent_per_week) VALUES (?, 'Black Box', 20)",
                   (str(uuid.uuid4()),))

    conn.commit()
    conn.close()
    print("✅ V2 Database created with UUIDs, Statuses, and Read-Only roles!")


if __name__ == '__main__':
    reset_database()