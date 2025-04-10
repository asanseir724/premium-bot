-- Add api_key_hash column
ALTER TABLE admin_user ADD COLUMN IF NOT EXISTS api_key_hash VARCHAR(256);

-- Add updated_at column
ALTER TABLE admin_user ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT NOW();