CREATE TABLE IF NOT EXISTS test_milestones (
    test_id VARCHAR(36) PRIMARY KEY REFERENCES tests(id) ON DELETE CASCADE,
    intake_status VARCHAR(20) DEFAULT 'Pending',     -- Expected values: 'Pending', 'Planned', 'Done'
    restitution_status VARCHAR(20) DEFAULT 'Pending', -- Expected values: 'Pending', 'Planned', 'Done'
    checklist_state JSONB DEFAULT '{}'::jsonb,       -- Stores the checked/unchecked state of specific requirements
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);