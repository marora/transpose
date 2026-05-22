"""add book_validation_reports table

Revision ID: 3a9e1b27c4f1
Revises: 2f8c4a91d3e7
Create Date: 2026-05-22 12:00:00.000000

Persists the JSON validation report produced by `_build_validation_report()`
at the end of every pipeline run so the admin dashboard (issue #99) can
surface gate pass/fail + duration_ms + failure reasons without re-reading
disk artifacts.

Schema design:
  - One row per pipeline run; ordered by created_at.
  - report jsonb contains the full report (gates[], overall, artifacts, timestamp).
  - We do NOT mutate existing rows — append-only history.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "3a9e1b27c4f1"
down_revision: Union[str, Sequence[str], None] = "2f8c4a91d3e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS book_validation_reports (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            book_id UUID NOT NULL REFERENCES books(id) ON DELETE CASCADE,
            overall TEXT NOT NULL CHECK (overall IN ('PASS', 'FAIL')),
            report JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS book_validation_reports_book_id_created_at_idx
        ON book_validation_reports (book_id, created_at DESC)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS book_validation_reports_book_id_created_at_idx")
    op.execute("DROP TABLE IF EXISTS book_validation_reports")
