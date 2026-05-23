"""add oracle_score column to book_validation_reports

Revision ID: 4b7d8e92f5a2
Revises: 3a9e1b27c4f1
Create Date: 2026-05-23 00:00:00.000000

Adds oracle_score JSONB column to book_validation_reports table for storing
Layer C quality assessment from Anthropic Claude Sonnet 4.5 judge.

Schema:
  - oracle_score: JSONB nullable column containing:
    - composite_score: 0-100 overall quality
    - fluency: 0-100 naturalness of English
    - cultural_register: 0-100 cultural term accuracy
    - terminology_nuance: 0-100 semantic richness preservation
    - sampled_chunk_ids: array of chunk UUIDs assessed
    - raw_judge_response: full JSON from Anthropic API
  - NULL when Layer C has not run or failed (post-export, non-blocking)
"""

from typing import Sequence, Union

from alembic import op

revision: str = "4b7d8e92f5a2"
down_revision: Union[str, Sequence[str], None] = "3a9e1b27c4f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE book_validation_reports
        ADD COLUMN IF NOT EXISTS oracle_score JSONB
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE book_validation_reports
        DROP COLUMN IF EXISTS oracle_score
        """
    )
