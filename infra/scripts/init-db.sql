-- init-db.sql
-- PostgreSQL schema for Transpose literary translation pipeline
-- Migration: Initial schema v1
-- Created: 2024
-- Run this after provisioning the infrastructure with the managed identity

-- ============================================================================
-- Core Tables
-- ============================================================================

-- Books table
CREATE TABLE IF NOT EXISTS books (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT NOT NULL,
    author TEXT,
    source_language TEXT NOT NULL CHECK (source_language IN ('hindi', 'punjabi')),
    source_hash TEXT NOT NULL UNIQUE,
    source_blob_uri TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ingested',
    page_count INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Pages table
CREATE TABLE IF NOT EXISTS pages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    book_id UUID NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    page_number INTEGER NOT NULL,
    raw_text TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 1.0,
    needs_review BOOLEAN NOT NULL DEFAULT FALSE,
    ocr_metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (book_id, page_number)
);

-- Chunks table
CREATE TABLE IF NOT EXISTS chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    book_id UUID NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL,
    source_text TEXT NOT NULL,
    token_count INTEGER NOT NULL,
    chapter_ref TEXT,
    section_type TEXT NOT NULL DEFAULT 'prose',
    page_start INTEGER NOT NULL,
    page_end INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (book_id, sequence)
);

-- Translations table
CREATE TABLE IF NOT EXISTS translations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chunk_id UUID NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    book_id UUID NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    translated_text TEXT NOT NULL,
    model_version TEXT NOT NULL,
    cultural_terms JSONB,
    prompt_tokens INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    raw_response JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (chunk_id)
);

-- Cultural terms table
CREATE TABLE IF NOT EXISTS cultural_terms (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    book_id UUID NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    term TEXT NOT NULL,
    original_script TEXT,
    definition TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('seed', 'llm_detected')),
    occurrence_count INTEGER NOT NULL DEFAULT 1,
    first_chapter TEXT,
    needs_review BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (book_id, term)
);

-- Glossaries table
CREATE TABLE IF NOT EXISTS glossaries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    book_id UUID NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    entries JSONB,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    version INTEGER NOT NULL DEFAULT 1,
    UNIQUE (book_id, version)
);

-- Manuscripts table
CREATE TABLE IF NOT EXISTS manuscripts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    book_id UUID NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    title TEXT,
    author TEXT,
    chapters JSONB,
    glossary_id UUID REFERENCES glossaries(id),
    table_of_contents JSONB,
    metadata JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Pipeline state table (replaces Redis pipeline state)
CREATE TABLE IF NOT EXISTS pipeline_state (
    book_id UUID NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    stage TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    progress_completed INTEGER NOT NULL DEFAULT 0,
    progress_total INTEGER NOT NULL DEFAULT 0,
    locked_at TIMESTAMPTZ,
    lock_expires_at TIMESTAMPTZ,
    error_message TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (book_id)
);

-- Pipeline locks table (row-based distributed locks with TTL)
CREATE TABLE IF NOT EXISTS pipeline_locks (
    book_id TEXT PRIMARY KEY,
    locked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    holder_id TEXT NOT NULL
);

-- Pipeline jobs table (persistent job status tracking)
CREATE TABLE IF NOT EXISTS pipeline_jobs (
    book_id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'accepted',
    stage TEXT,
    error TEXT,
    result JSONB,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- ============================================================================
-- Indexes for Query Performance
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_pages_book_id ON pages(book_id);
CREATE INDEX IF NOT EXISTS idx_chunks_book_id ON chunks(book_id);
CREATE INDEX IF NOT EXISTS idx_translations_book_id ON translations(book_id);
CREATE INDEX IF NOT EXISTS idx_cultural_terms_book_id ON cultural_terms(book_id);
CREATE INDEX IF NOT EXISTS idx_books_status ON books(status);
CREATE INDEX IF NOT EXISTS idx_chunks_sequence ON chunks(book_id, sequence);
CREATE INDEX IF NOT EXISTS idx_pages_page_number ON pages(book_id, page_number);
CREATE INDEX IF NOT EXISTS idx_pipeline_state_status ON pipeline_state(status);
CREATE INDEX IF NOT EXISTS idx_pipeline_locks_expires ON pipeline_locks(expires_at);
CREATE INDEX IF NOT EXISTS idx_pipeline_jobs_status ON pipeline_jobs(status);

-- ============================================================================
-- Triggers for updated_at timestamp
-- ============================================================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_books_updated_at
    BEFORE UPDATE ON books
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Add updated_at trigger for pipeline_state
CREATE TRIGGER update_pipeline_state_updated_at
    BEFORE UPDATE ON pipeline_state
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- Comments for documentation
-- ============================================================================

COMMENT ON TABLE books IS 'Master table for source books being translated';
COMMENT ON TABLE pages IS 'OCR-extracted text and metadata for each page';
COMMENT ON TABLE chunks IS 'Translation-ready text units with semantic boundaries';
COMMENT ON TABLE translations IS 'Translated chunks with LLM metadata and token usage';
COMMENT ON TABLE cultural_terms IS 'Preserved culturally significant terms with definitions';
COMMENT ON TABLE glossaries IS 'Aggregated glossary per book version';
COMMENT ON TABLE manuscripts IS 'Assembled translated documents ready for export';
COMMENT ON TABLE pipeline_state IS 'Pipeline execution state — replaces Redis for status tracking and locking';
COMMENT ON TABLE pipeline_locks IS 'Row-based distributed locks with TTL enforcement for pipeline concurrency';
COMMENT ON TABLE pipeline_jobs IS 'Persistent job status tracking for the HTTP API';

-- ============================================================================
-- Verification Query
-- ============================================================================

-- Run this to verify all tables were created successfully:
SELECT 
    schemaname,
    tablename,
    tableowner
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY tablename;
