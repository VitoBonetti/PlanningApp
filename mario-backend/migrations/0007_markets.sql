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