CREATE TABLE test_documents (
    id VARCHAR(36) PRIMARY KEY,
    test_id VARCHAR(36) REFERENCES tests(id) ON DELETE CASCADE,
    drive_file_id VARCHAR(255) UNIQUE NOT NULL,
    file_name VARCHAR(500) NOT NULL,
    mime_type VARCHAR(100),
    file_url TEXT NOT NULL,
    last_modified TIMESTAMP,
    synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for fast searching by test
CREATE INDEX idx_test_documents_test_id ON test_documents(test_id);