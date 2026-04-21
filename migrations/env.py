"""Alembic environment configuration for Transpose.

Resolves the database URL from TRANSPOSE_* environment variables
(matching the pydantic Settings in src/transpose/config/settings.py).

Priority:
  1. TRANSPOSE_DATABASE_URL (full DSN override)
  2. Individual TRANSPOSE_POSTGRES_* variables assembled into a DSN
  3. alembic.ini sqlalchemy.url (fallback for local dev)
"""

import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None


def _get_url() -> str:
    """Build a PostgreSQL connection URL from environment variables."""
    # Full DSN override
    url = os.environ.get("TRANSPOSE_DATABASE_URL")
    if url:
        return url

    # Assemble from individual TRANSPOSE_POSTGRES_* vars
    host = os.environ.get("TRANSPOSE_POSTGRES_HOST", "localhost")
    port = os.environ.get("TRANSPOSE_POSTGRES_PORT", "5432")
    db = os.environ.get("TRANSPOSE_POSTGRES_DB", "transpose")
    user = os.environ.get("TRANSPOSE_POSTGRES_USER", "transpose")
    password = os.environ.get("TRANSPOSE_POSTGRES_PASSWORD", "")

    if password:
        return f"postgresql://{user}:{password}@{host}:{port}/{db}"
    return f"postgresql://{user}@{host}:{port}/{db}"


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (no DB connection needed)."""
    url = _get_url() or config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode with a live DB connection."""
    url = _get_url()
    if url:
        config.set_main_option("sqlalchemy.url", url)

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
