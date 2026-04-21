CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT UNIQUE,
    hashed_password TEXT,
    name TEXT,
    role TEXT,
    location TEXT,
    base_capacity REAL,
    start_week INTEGER DEFAULT 1,
    session_token TEXT DEFAULT '' 
);

CREATE TABLE IF NOT EXISTS services (
    id TEXT PRIMARY KEY,
    name TEXT,
    max_concurrent_per_week INTEGER
);

CREATE TABLE IF NOT EXISTS tests (
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
);

CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    user_id TEXT,
    event_type TEXT,
    location TEXT,
    start_date TEXT,
    end_date TEXT
);

CREATE TABLE IF NOT EXISTS assignments (
    id TEXT PRIMARY KEY,
    test_id TEXT,
    user_id TEXT,
    week_number INTEGER,
    year INTEGER,
    allocated_credits REAL
);

CREATE TABLE IF NOT EXISTS assets (
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
);

CREATE TABLE IF NOT EXISTS test_assets (
    test_id TEXT REFERENCES tests(id),
    asset_id TEXT REFERENCES assets(id)
);

CREATE TABLE IF NOT EXISTS notifications (
    id TEXT PRIMARY KEY,
    user_id TEXT,
    message TEXT,
    type TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_read BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS test_history (
    id TEXT PRIMARY KEY,
    test_id TEXT REFERENCES tests(id) ON DELETE CASCADE,
    action TEXT,
    week_number INTEGER,
    year INTEGER,
    changed_by_user_id TEXT,
    changed_by_username TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS raw_assets (
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
);

