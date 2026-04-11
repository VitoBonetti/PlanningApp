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