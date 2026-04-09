
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