"""baseline schema

Revision ID: 0001_baseline
Revises:
Create Date: 2026-04-25
"""
from alembic import op

revision = '0001_baseline'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Copy all the CREATE TABLE statements from your old .sql files and paste them here
    op.execute("""
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
        
        ALTER TABLE users DROP COLUMN IF EXISTS hashed_password;
        ALTER TABLE users DROP COLUMN IF EXISTS session_token;
        
        ALTER TABLE users ADD COLUMN IF NOT EXISTS start_year INTEGER DEFAULT 2024;
        ALTER TABLE users ADD COLUMN IF NOT EXISTS end_week INTEGER DEFAULT NULL;
        ALTER TABLE users ADD COLUMN IF NOT EXISTS end_year INTEGER DEFAULT NULL;
        
        CREATE TABLE IF NOT EXISTS whitebox_categories (
            id UUID PRIMARY KEY,
            name VARCHAR(255) UNIQUE NOT NULL,
            target_goal INTEGER DEFAULT 0
        );
        
        INSERT INTO whitebox_categories (id, name, target_goal) VALUES
        (gen_random_uuid(), 'Crown Jewels', 40),
        (gen_random_uuid(), 'X-One Global', 30),
        (gen_random_uuid(), 'AI', 12),
        (gen_random_uuid(), 'Market Jewels', 10),
        (gen_random_uuid(), 'GIS', 10),
        (gen_random_uuid(), 'Digital', 5),
        (gen_random_uuid(), 'Mobile', 3)
        ON CONFLICT (name) DO NOTHING;
        
        ALTER TABLE tests ADD COLUMN drive_folder_id VARCHAR(255);
        ALTER TABLE tests ADD COLUMN drive_folder_url TEXT;
        
        CREATE TABLE IF NOT EXISTS test_documents (
            id VARCHAR(36) PRIMARY KEY,
            test_id VARCHAR(36) REFERENCES tests(id) ON DELETE CASCADE,
            drive_file_id VARCHAR(255) UNIQUE NOT NULL,
            file_name VARCHAR(500) NOT NULL,
            mime_type VARCHAR(100),
            file_url TEXT NOT NULL,
            last_modified TIMESTAMP,
            synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE INDEX idx_test_documents_test_id ON test_documents(test_id);
        
        CREATE TABLE IF NOT EXISTS  markets (
            id VARCHAR(36) PRIMARY KEY,
            code VARCHAR(10) UNIQUE NOT NULL, -- Maps to the existing asset.market field
            name VARCHAR(100) NOT NULL,
            language VARCHAR(50) DEFAULT 'English',
            region VARCHAR(50),
            is_active BOOLEAN DEFAULT TRUE,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        INSERT INTO markets (id, code, name, description)
        SELECT gen_random_uuid()::varchar, market, market, 'Auto-imported from existing assets'
        FROM assets
        WHERE market IS NOT NULL AND market != ''
        ON CONFLICT (code) DO NOTHING;
        
        CREATE TABLE IF NOT EXISTS  regions (
            id VARCHAR(36) PRIMARY KEY,
            regions VARCHAR(50) UNIQUE NOT NULL,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        INSERT INTO regions (id, regions) VALUES
        (gen_random_uuid(), 'Apac'),
        (gen_random_uuid(), 'Digital'),
        (gen_random_uuid(), 'Enter'),
        (gen_random_uuid(), 'GIS'),
        (gen_random_uuid(), 'Holding'),
        (gen_random_uuid(), 'Latin America'),
        (gen_random_uuid(), 'North America'),
        (gen_random_uuid(), 'North Europe'),
        (gen_random_uuid(), 'South Europe')
        ON CONFLICT (regions) DO NOTHING;
        
        CREATE TABLE IF NOT EXISTS market_contacts (
            id VARCHAR(36) PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            email VARCHAR(100) UNIQUE NOT NULL,
            platform_role VARCHAR(50) DEFAULT 'market_user',
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        
        CREATE TABLE IF NOT EXISTS market_contact_assignments (
            id VARCHAR(36) PRIMARY KEY,
            contact_id VARCHAR(36) REFERENCES market_contacts(id) ON DELETE CASCADE,
            market_id VARCHAR(36) REFERENCES markets(id) ON DELETE CASCADE,
            market_role VARCHAR(50) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (contact_id, market_id, market_role)
        );
        
        CREATE TABLE IF NOT EXISTS test_milestones (
            test_id VARCHAR(36) PRIMARY KEY REFERENCES tests(id) ON DELETE CASCADE,
            intake_status VARCHAR(20) DEFAULT 'Pending',     
            restitution_status VARCHAR(20) DEFAULT 'Pending', 
            checklist_state JSONB DEFAULT '{}'::jsonb,      
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE TABLE IF NOT EXISTS intake_notes (
            id TEXT PRIMARY KEY,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            
            status TEXT DEFAULT 'PENDING', 
            
            file_path TEXT, 
            original_filename TEXT,
            source_type TEXT, 
            uploaded_by TEXT, 
          
            ai_raw_text TEXT,               
            ai_summary TEXT,                
            ai_best_guess_asset_id TEXT,    
            ai_best_guess_market TEXT,      
            ai_confidence INTEGER,            
            
            ai_alternative_matches TEXT     
        );
        
        ALTER TABLE intake_notes ADD COLUMN IF NOT EXISTS ai_extracted_assets JSONB;
    """)


def downgrade():
    pass