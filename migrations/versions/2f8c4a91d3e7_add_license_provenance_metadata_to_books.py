"""add license, provenance, metadata columns to books

Revision ID: 2f8c4a91d3e7
Revises: bbbf3659ac87
Create Date: 2026-05-20 23:19:30.952000

Addresses two gaps called out in the workspace/license architecture decisions
(decisions.md, 2026-05-20T22:52 and 2026-05-20T23:10):

  1. books.metadata JSONB was missing from the baseline migration — latent bug.
  2. license_status, provenance_source, and license_history are required to
     enforce the 4-layer rights-unknown rule and per-book promotion gate.

Backfill strategy for existing rows:
  - license_status     → 'rights-unknown' (safe default; Manish reviews each book)
  - provenance_source  → JSON object seeded from source_blob_uri / created_at
  - metadata           → '{}' (empty; pipeline will populate on next workspace write)
  - license_history    → '[]' (empty array; mutations will append going forward)
"""

from typing import Sequence, Union

from alembic import op

revision: str = '2f8c4a91d3e7'
down_revision: Union[str, Sequence[str], None] = 'bbbf3659ac87'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. books.metadata ─────────────────────────────────────────────────────
    # The baseline migration declared this column in the architecture notes but
    # never landed the DDL.  Add it idempotently so a partially-migrated DB
    # is safe to upgrade.
    op.execute("""
        ALTER TABLE books
            ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'
    """)

    # ── 2. books.license_status ───────────────────────────────────────────────
    # Four-value enum enforced at the DB layer.  NOT NULL + default means every
    # new row starts as rights-unknown without explicit caller action.
    op.execute("""
        ALTER TABLE books
            ADD COLUMN IF NOT EXISTS license_status TEXT
                NOT NULL DEFAULT 'rights-unknown'
    """)

    # Add the CHECK constraint separately so it works even if the column was
    # previously added without the constraint.  DROP + ADD is idempotent here
    # because we name the constraint explicitly.
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'chk_books_license_status'
            ) THEN
                ALTER TABLE books
                    ADD CONSTRAINT chk_books_license_status
                    CHECK (license_status IN (
                        'rights-unknown',
                        'claimed-public-domain',
                        'verified-public-domain',
                        'rights-cleared'
                    ));
            END IF;
        END $$
    """)

    # Index on license_status supports the promotion-gate query:
    #   SELECT * FROM books
    #   WHERE license_status IN ('verified-public-domain', 'rights-cleared')
    #     AND status = 'published';
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_books_license_status
            ON books (license_status)
    """)

    # ── 3. books.provenance_source ────────────────────────────────────────────
    # Stores: { url, edition, acquired_at, notes } — see decisions.md §B
    op.execute("""
        ALTER TABLE books
            ADD COLUMN IF NOT EXISTS provenance_source JSONB
    """)

    # ── 4. books.license_history ──────────────────────────────────────────────
    # Append-only mutation log.  Every license_status change by Manish adds an
    # entry: { timestamp, field, from, to, actor, note }.
    op.execute("""
        ALTER TABLE books
            ADD COLUMN IF NOT EXISTS license_history JSONB
                NOT NULL DEFAULT '[]'::jsonb
    """)

    # ── 5. Backfill existing rows ─────────────────────────────────────────────
    # license_status: already defaulted; explicit set guards any existing row
    #   that somehow slipped through without the default.
    #
    # provenance_source: best-effort seed from source_blob_uri + created_at.
    #   - url: source_blob_uri if it starts with 'http', else null
    #   - edition: null (must be filled by Manish per-book)
    #   - acquired_at: created_at as ISO-8601 proxy
    #   - notes: null
    #
    # metadata and license_history: already defaulted; no additional UPDATE
    #   needed unless a pre-default row exists.
    op.execute("""
        UPDATE books
        SET
            license_status = 'rights-unknown',
            provenance_source = jsonb_build_object(
                'url',
                CASE
                    WHEN source_blob_uri ILIKE 'http%' THEN source_blob_uri
                    ELSE NULL
                END,
                'edition',  NULL,
                'acquired_at', to_char(created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
                'notes',    NULL
            ),
            metadata = COALESCE(metadata, '{}'),
            license_history = COALESCE(license_history, '[]'::jsonb)
        WHERE
            license_status IS NULL
            OR provenance_source IS NULL
            OR metadata IS NULL
            OR license_history IS NULL
    """)

    # ── 6. CHECK CONSTRAINT REGRESSION TEST ───────────────────────────────────
    # Inline DO-block: attempts to INSERT a row with an invalid license_status
    # value, asserts the DB raises an exception, then rolls back.
    # If this block raises an unexpected error (i.e. the constraint is absent),
    # the migration itself will fail — catching the regression at migration time.
    op.execute("""
        DO $$
        DECLARE
            _raised BOOLEAN := FALSE;
        BEGIN
            BEGIN
                INSERT INTO books (
                    title, source_language, source_hash, source_blob_uri,
                    license_status
                ) VALUES (
                    '__constraint_test__', 'hindi',
                    'sha256_constraint_test_dummy_' || gen_random_uuid()::text,
                    'blob://test',
                    'invalid-status-value'
                );
            EXCEPTION WHEN check_violation THEN
                _raised := TRUE;
            END;

            IF NOT _raised THEN
                RAISE EXCEPTION
                    'MIGRATION SELF-TEST FAILED: chk_books_license_status '
                    'did not reject invalid value "invalid-status-value". '
                    'The CHECK constraint is missing or malformed.';
            END IF;
        END $$
    """)


def downgrade() -> None:
    # Remove columns in reverse order.  DROP INDEX / DROP CONSTRAINT first.
    op.execute("DROP INDEX IF EXISTS idx_books_license_status")
    op.execute("""
        ALTER TABLE books
            DROP CONSTRAINT IF EXISTS chk_books_license_status
    """)
    op.execute("ALTER TABLE books DROP COLUMN IF EXISTS license_history")
    op.execute("ALTER TABLE books DROP COLUMN IF EXISTS provenance_source")
    op.execute("ALTER TABLE books DROP COLUMN IF EXISTS license_status")
    op.execute("ALTER TABLE books DROP COLUMN IF EXISTS metadata")
