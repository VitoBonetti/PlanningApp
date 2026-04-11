CREATE TABLE IF NOT EXISTS intake_notes (
    id TEXT PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Workflow state: PENDING, REVIEW_READY, PROCESSED, DISCARDED
    status TEXT DEFAULT 'PENDING', 
    
    -- Storage details
    file_path TEXT, 
    original_filename TEXT,
    source_type TEXT, -- e.g., 'IMAGE', 'TEXT', 'PDF'
    uploaded_by TEXT, -- Username of the admin who dropped it
    
    -- AI Extracted Data
    ai_raw_text TEXT,               -- The OCR'd or pasted raw text
    ai_summary TEXT,                -- A short 1-sentence summary of the request
    ai_best_guess_asset_id TEXT,    -- The UUID of the asset it thinks this is
    ai_best_guess_market TEXT,      -- The Market code (e.g., 'US', 'FR')
    ai_confidence INTEGER,          -- 0-100 confidence score
    
    -- JSON holding alternative asset IDs and reasons in case the Best Guess is wrong
    ai_alternative_matches TEXT     
);