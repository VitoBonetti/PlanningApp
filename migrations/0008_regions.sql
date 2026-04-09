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