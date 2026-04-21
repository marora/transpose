"""baseline schema

Revision ID: bbbf3659ac87
Revises:
Create Date: 2026-04-21 12:47:53.977289

NOTE: This is a BASELINE migration capturing the existing Transpose schema.
If your database already has these tables (e.g., from init-db.sql), stamp
this migration without running it:

    alembic stamp bbbf3659ac87

All tables use CREATE TABLE IF NOT EXISTS so this migration is safe to run
against an existing database — it will not drop or alter existing data.
"""

from typing import Sequence, Union

from alembic import op

revision: str = 'bbbf3659ac87'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create all Transpose tables — safe against existing schemas."""
    # ── Core Tables ──────────────────────────────────────────────
    op.execute("""
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
        )
    """)

    op.execute("""
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
        )
    """)

    op.execute("""
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
        )
    """)

    op.execute("""
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
        )
    """)

    op.execute("""
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
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS glossaries (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            book_id UUID NOT NULL REFERENCES books(id) ON DELETE CASCADE,
            entries JSONB,
            generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            version INTEGER NOT NULL DEFAULT 1,
            UNIQUE (book_id, version)
        )
    """)

    op.execute("""
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
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS pipeline_state (
            book_id UUID NOT NULL REFERENCES books(id) ON DELETE CASCADE,
            stage TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'running', 'completed', 'failed')),
            progress_completed INTEGER NOT NULL DEFAULT 0,
            progress_total INTEGER NOT NULL DEFAULT 0,
            locked_at TIMESTAMPTZ,
            lock_expires_at TIMESTAMPTZ,
            error_message TEXT,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (book_id)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS pipeline_locks (
            book_id TEXT PRIMARY KEY,
            locked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            expires_at TIMESTAMPTZ NOT NULL,
            holder_id TEXT NOT NULL
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS pipeline_jobs (
            book_id TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'accepted',
            stage TEXT,
            error TEXT,
            result JSONB,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS book_costs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            book_id UUID NOT NULL,
            service TEXT NOT NULL,
            metric TEXT NOT NULL,
            quantity BIGINT NOT NULL,
            estimated_cost_usd NUMERIC(10, 6),
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """)

    # ── Indexes ──────────────────────────────────────────────────
    op.execute("CREATE INDEX IF NOT EXISTS idx_pages_book_id ON pages(book_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_chunks_book_id ON chunks(book_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_translations_book_id ON translations(book_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_cultural_terms_book_id ON cultural_terms(book_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_books_status ON books(status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_chunks_sequence ON chunks(book_id, sequence)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_pages_page_number ON pages(book_id, page_number)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_pipeline_state_status ON pipeline_state(status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_pipeline_locks_expires ON pipeline_locks(expires_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_pipeline_jobs_status ON pipeline_jobs(status)")

    # ── Triggers ─────────────────────────────────────────────────
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)

    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_trigger WHERE tgname = 'update_books_updated_at'
            ) THEN
                CREATE TRIGGER update_books_updated_at
                    BEFORE UPDATE ON books
                    FOR EACH ROW
                    EXECUTE FUNCTION update_updated_at_column();
            END IF;
        END $$
    """)

    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_trigger WHERE tgname = 'update_pipeline_state_updated_at'
            ) THEN
                CREATE TRIGGER update_pipeline_state_updated_at
                    BEFORE UPDATE ON pipeline_state
                    FOR EACH ROW
                    EXECUTE FUNCTION update_updated_at_column();
            END IF;
        END $$
    """)


def downgrade() -> None:
    """Drop all Transpose tables in reverse dependency order."""
    op.execute("DROP TABLE IF EXISTS book_costs CASCADE")
    op.execute("DROP TABLE IF EXISTS pipeline_jobs CASCADE")
    op.execute("DROP TABLE IF EXISTS pipeline_locks CASCADE")
    op.execute("DROP TABLE IF EXISTS pipeline_state CASCADE")
    op.execute("DROP TABLE IF EXISTS manuscripts CASCADE")
    op.execute("DROP TABLE IF EXISTS glossaries CASCADE")
    op.execute("DROP TABLE IF EXISTS cultural_terms CASCADE")
    op.execute("DROP TABLE IF EXISTS translations CASCADE")
    op.execute("DROP TABLE IF EXISTS chunks CASCADE")
    op.execute("DROP TABLE IF EXISTS pages CASCADE")
    op.execute("DROP TABLE IF EXISTS books CASCADE")
    op.execute("DROP FUNCTION IF EXISTS update_updated_at_column() CASCADE")
