-- Initialize pgvector extension for InTEAM AI Service
-- This script runs automatically when PostgreSQL container first starts

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Log successful initialization
DO $$
BEGIN
    RAISE NOTICE 'pgvector extension enabled successfully for InTEAM AI Service';
END $$;
