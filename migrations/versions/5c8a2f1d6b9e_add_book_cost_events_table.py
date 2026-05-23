"""add book_cost_events table

Revision ID: 5c8a2f1d6b9e
Revises: 4b7d8e92f5a2
Create Date: 2026-05-24 00:00:00.000000

Adds append-only book_cost_events table for stage-level cost telemetry
(closes #97 / #93).

Schema:
  - id (UUID): primary key, one row per (book, run, stage)
  - book_id (UUID): foreign key intent (no FK constraint to avoid cascade issues)
  - run_id (UUID): generated once per pipeline invocation; resumes get a fresh UUID
  - stage_name (TEXT): ingest | ocr | chunk | translate | glossary | assemble | export | workspace
  - started_at / ended_at (TIMESTAMPTZ): ended_at IS NULL for interrupted runs
  - input_tokens / output_tokens / ocr_pages / blob_read_ops / blob_write_ops (INT)
  - estimated_cost_usd (NUMERIC(10,6))
  - retries (INT)
  - status (TEXT): started | completed | failed
  - error_message (TEXT)

Indexes:
  - (book_id) for "all events for a book" queries
  - (book_id, stage_name) for per-stage aggregations
  - (run_id) for grouping events from a single pipeline invocation
"""

from collections.abc import Sequence

from alembic import op

revision: str = "5c8a2f1d6b9e"
down_revision: str | Sequence[str] | None = "4b7d8e92f5a2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS book_cost_events (
            id UUID PRIMARY KEY,
            book_id UUID NOT NULL,
            run_id UUID NOT NULL,
            stage_name TEXT NOT NULL,
            started_at TIMESTAMPTZ NOT NULL,
            ended_at TIMESTAMPTZ,
            input_tokens INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0,
            ocr_pages INTEGER NOT NULL DEFAULT 0,
            blob_read_ops INTEGER NOT NULL DEFAULT 0,
            blob_write_ops INTEGER NOT NULL DEFAULT 0,
            estimated_cost_usd NUMERIC(10,6) NOT NULL DEFAULT 0,
            retries INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'started',
            error_message TEXT
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_book_cost_events_book "
        "ON book_cost_events(book_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_book_cost_events_book_stage "
        "ON book_cost_events(book_id, stage_name)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_book_cost_events_run "
        "ON book_cost_events(run_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_book_cost_events_run")
    op.execute("DROP INDEX IF EXISTS idx_book_cost_events_book_stage")
    op.execute("DROP INDEX IF EXISTS idx_book_cost_events_book")
    op.execute("DROP TABLE IF EXISTS book_cost_events")
