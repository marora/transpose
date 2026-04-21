"""PostgreSQL database connection and query helpers."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import asyncpg

from transpose.models.book import Book, Page
from transpose.models.enums import BookStatus, SectionType, SourceLanguage, TermSource
from transpose.models.glossary import Glossary, GlossaryEntry
from transpose.models.manuscript import Chapter, Manuscript
from transpose.models.translation import Chunk, CulturalTerm, ExtractedTerm, Translation


class Database:
    """Async PostgreSQL connection pool.

    Uses asyncpg for high-performance async queries.
    Supports Managed Identity auth via Entra token or password fallback.
    """

    def __init__(self, dsn: str, *, pool_min_size: int = 5, pool_max_size: int = 20) -> None:
        self._dsn = dsn
        self._pool: asyncpg.Pool | None = None
        self._pool_min_size = pool_min_size
        self._pool_max_size = pool_max_size

    async def connect(self, ssl: str | None = None) -> None:
        """Initialize the connection pool with keepalive for long-running pipelines."""
        kwargs: dict = {
            "dsn": self._dsn,
            "min_size": self._pool_min_size,
            "max_size": self._pool_max_size,
            "command_timeout": 60,
            # TCP keepalive to prevent Azure PostgreSQL idle disconnects
            "server_settings": {
                "tcp_keepalives_idle": "60",
                "tcp_keepalives_interval": "15",
                "tcp_keepalives_count": "4",
            },
        }
        if ssl:
            kwargs["ssl"] = ssl
        self._pool = await asyncpg.create_pool(**kwargs)

    async def close(self) -> None:
        """Close the connection pool."""
        if self._pool is not None:
            await self._pool.close()

    @property
    def pool(self) -> asyncpg.Pool:
        """Access the connection pool. Raises if not connected."""
        if self._pool is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._pool

    async def execute(self, query: str, *args) -> str:
        """Execute a query with retry on transient connection errors."""
        return await self._retry(self._execute_inner, query, *args)

    async def _execute_inner(self, query: str, *args) -> str:
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)

    async def fetch_one(self, query: str, *args) -> asyncpg.Record | None:
        """Execute a query and return a single row, with retry."""
        return await self._retry(self._fetch_one_inner, query, *args)

    async def _fetch_one_inner(self, query: str, *args) -> asyncpg.Record | None:
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def _retry(self, func, *args, max_attempts: int = 3):
        """Retry a DB operation on transient connection errors."""
        import asyncio

        for attempt in range(max_attempts):
            try:
                return await func(*args)
            except (
                asyncpg.ConnectionDoesNotExistError,
                asyncpg.InterfaceError,
                ConnectionResetError,
                OSError,
            ):
                if attempt == max_attempts - 1:
                    raise
                wait = 2 ** attempt
                import logging
                logging.getLogger(__name__).warning(
                    "DB connection error (attempt %d/%d), retrying in %ds",
                    attempt + 1, max_attempts, wait,
                )
                await asyncio.sleep(wait)

    async def fetch_many(self, query: str, *args) -> list[asyncpg.Record]:
        """Execute a query and return all rows, with retry."""
        async def _inner():
            async with self.pool.acquire() as conn:
                return await conn.fetch(query, *args)
        return await self._retry(_inner)

    async def execute_many(self, query: str, args_list: list[tuple]) -> None:
        """Execute a query for multiple arg sets, with retry."""
        async def _inner():
            async with self.pool.acquire() as conn:
                await conn.executemany(query, args_list)
        return await self._retry(_inner)

    # --- Book CRUD ---

    async def create_book(self, book: Book) -> None:
        """Create a new book record."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO books (
                    id, title, author, source_language, source_hash, 
                    source_blob_uri, status, page_count, created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                """,
                book.id,
                book.title,
                book.author,
                book.source_language.value,
                book.source_hash,
                book.source_blob_uri,
                book.status.value,
                book.page_count,
                book.created_at,
                book.updated_at,
            )

    async def get_book(self, book_id: UUID) -> Book | None:
        """Get a book by ID."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM books WHERE id = $1", book_id)
            if not row:
                return None
            return Book(
                id=row["id"],
                title=row["title"],
                author=row["author"],
                source_language=SourceLanguage(row["source_language"]),
                source_hash=row["source_hash"],
                source_blob_uri=row["source_blob_uri"],
                status=BookStatus(row["status"]),
                page_count=row["page_count"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    async def get_book_by_hash(self, source_hash: str) -> Book | None:
        """Get a book by source hash (for deduplication)."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM books WHERE source_hash = $1", source_hash)
            if not row:
                return None
            return Book(
                id=row["id"],
                title=row["title"],
                author=row["author"],
                source_language=SourceLanguage(row["source_language"]),
                source_hash=row["source_hash"],
                source_blob_uri=row["source_blob_uri"],
                status=BookStatus(row["status"]),
                page_count=row["page_count"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    async def update_book_status(
        self, book_id: UUID, status: BookStatus, updated_at: datetime | None = None
    ) -> None:
        """Update a book's status."""
        if updated_at is None:
            from datetime import UTC

            updated_at = datetime.now(UTC)

        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE books SET status = $1, updated_at = $2 WHERE id = $3",
                status.value,
                updated_at,
                book_id,
            )

    async def update_book_page_count(self, book_id: UUID, page_count: int) -> None:
        """Update a book's page count."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE books SET page_count = $1 WHERE id = $2",
                page_count,
                book_id,
            )

    # --- Page CRUD ---

    async def create_pages(self, pages: list[Page]) -> None:
        """Create multiple page records."""
        import json

        if not pages:
            return

        async with self.pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO pages (
                    id, book_id, page_number, raw_text, confidence, 
                    needs_review, ocr_metadata, created_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                [
                    (
                        page.id,
                        page.book_id,
                        page.page_number,
                        page.raw_text,
                        page.confidence,
                        page.needs_review,
                        json.dumps(page.ocr_metadata),
                        page.created_at,
                    )
                    for page in pages
                ],
            )

    async def get_pages_for_book(self, book_id: UUID) -> list[Page]:
        """Get all pages for a book, ordered by page number."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM pages WHERE book_id = $1 ORDER BY page_number",
                book_id,
            )
            return [
                Page(
                    id=row["id"],
                    book_id=row["book_id"],
                    page_number=row["page_number"],
                    raw_text=row["raw_text"],
                    confidence=row["confidence"],
                    needs_review=row["needs_review"],
                    ocr_metadata=row["ocr_metadata"],
                    created_at=row["created_at"],
                )
                for row in rows
            ]

    async def get_existing_page_numbers(self, book_id: UUID) -> set[int]:
        """Get page numbers that already exist for a book."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT page_number FROM pages WHERE book_id = $1",
                book_id,
            )
            return {row["page_number"] for row in rows}

    # --- Chunk CRUD ---

    async def create_chunks(self, chunks: list[Chunk]) -> None:
        """Create multiple chunk records."""
        if not chunks:
            return

        async with self.pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO chunks (
                    id, book_id, sequence, source_text, token_count,
                    page_start, page_end, section_type, chapter_ref, created_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                """,
                [
                    (
                        chunk.id,
                        chunk.book_id,
                        chunk.sequence,
                        chunk.source_text,
                        chunk.token_count,
                        chunk.page_start,
                        chunk.page_end,
                        chunk.section_type.value,
                        chunk.chapter_ref,
                        chunk.created_at,
                    )
                    for chunk in chunks
                ],
            )

    async def get_chunks_for_book(self, book_id: UUID) -> list[Chunk]:
        """Get all chunks for a book, ordered by sequence."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM chunks WHERE book_id = $1 ORDER BY sequence",
                book_id,
            )
            return [
                Chunk(
                    id=row["id"],
                    book_id=row["book_id"],
                    sequence=row["sequence"],
                    source_text=row["source_text"],
                    token_count=row["token_count"],
                    page_start=row["page_start"],
                    page_end=row["page_end"],
                    section_type=SectionType(row["section_type"]),
                    chapter_ref=row["chapter_ref"],
                    created_at=row["created_at"],
                )
                for row in rows
            ]

    async def delete_chunks_for_book(self, book_id: UUID) -> None:
        """Delete all chunks for a book (for re-chunking)."""
        async with self.pool.acquire() as conn:
            await conn.execute("DELETE FROM chunks WHERE book_id = $1", book_id)

    # --- Translation CRUD ---

    async def create_translation(self, translation: Translation) -> None:
        """Create a translation record (with connection retry)."""
        import json

        terms_json = json.dumps(
            [
                {
                    "term": term.term,
                    "original_script": term.original_script,
                    "definition": term.definition,
                    "source": term.source.value,
                }
                for term in translation.cultural_terms
            ]
        )

        await self.execute(
            """
            INSERT INTO translations (
                id, chunk_id, book_id, translated_text, model_version,
                cultural_terms, prompt_tokens, completion_tokens, raw_response, created_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            """,
            translation.id,
            translation.chunk_id,
            translation.book_id,
            translation.translated_text,
            translation.model_version,
            terms_json,
            translation.prompt_tokens,
            translation.completion_tokens,
            json.dumps(translation.raw_response) if isinstance(translation.raw_response, dict) else translation.raw_response,
            translation.created_at,
        )

    async def get_translations_for_book(self, book_id: UUID) -> list[Translation]:
        """Get all translations for a book, ordered by chunk sequence."""
        import json

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT t.* FROM translations t
                JOIN chunks c ON t.chunk_id = c.id
                WHERE t.book_id = $1
                ORDER BY c.sequence
                """,
                book_id,
            )
            translations = []
            for row in rows:
                # Parse cultural terms from JSON
                terms_data = json.loads(row["cultural_terms"]) if row["cultural_terms"] else []
                cultural_terms = [
                    ExtractedTerm(
                        term=term["term"],
                        original_script=term["original_script"],
                        definition=term["definition"],
                        source=TermSource(term["source"]),
                    )
                    for term in terms_data
                ]

                translations.append(
                    Translation(
                        id=row["id"],
                        chunk_id=row["chunk_id"],
                        book_id=row["book_id"],
                        translated_text=row["translated_text"],
                        model_version=row["model_version"],
                        cultural_terms=cultural_terms,
                        prompt_tokens=row["prompt_tokens"],
                        completion_tokens=row["completion_tokens"],
                        raw_response=row["raw_response"],
                        created_at=row["created_at"],
                    )
                )
            return translations

    async def get_translated_chunk_ids(self, book_id: UUID) -> set[UUID]:
        """Get chunk IDs that already have translations."""
        rows = await self.fetch_many(
            "SELECT chunk_id FROM translations WHERE book_id = $1",
            book_id,
        )
        return {row["chunk_id"] for row in rows}

    async def get_failed_translation_chunk_ids(self, book_id: UUID) -> set[UUID]:
        """Get chunk IDs that have placeholder/failed translations."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT chunk_id FROM translations
                   WHERE book_id = $1
                   AND translated_text LIKE '[TRANSLATION FAILED%'""",
                book_id,
            )
            return {row["chunk_id"] for row in rows}

    async def delete_translation(self, chunk_id: UUID) -> None:
        """Delete a translation record for re-translation."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM translations WHERE chunk_id = $1",
                chunk_id,
            )

    # --- Cultural Term CRUD ---

    async def upsert_cultural_term(self, term: CulturalTerm) -> None:
        """Insert or update a cultural term."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO cultural_terms (
                    id, book_id, term, definition, original_script,
                    source, occurrence_count, first_chapter, needs_review, created_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                ON CONFLICT (book_id, term) DO UPDATE SET
                    definition = EXCLUDED.definition,
                    occurrence_count = EXCLUDED.occurrence_count,
                    needs_review = EXCLUDED.needs_review
                """,
                term.id,
                term.book_id,
                term.term,
                term.definition,
                term.original_script,
                term.source.value,
                term.occurrence_count,
                term.first_chapter,
                term.needs_review,
                term.created_at,
            )

    async def get_cultural_terms_for_book(self, book_id: UUID) -> list[CulturalTerm]:
        """Get all cultural terms for a book."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM cultural_terms WHERE book_id = $1 ORDER BY term",
                book_id,
            )
            return [
                CulturalTerm(
                    id=row["id"],
                    book_id=row["book_id"],
                    term=row["term"],
                    definition=row["definition"],
                    original_script=row["original_script"],
                    source=TermSource(row["source"]),
                    occurrence_count=row["occurrence_count"],
                    first_chapter=row["first_chapter"],
                    needs_review=row["needs_review"],
                    created_at=row["created_at"],
                )
                for row in rows
            ]

    # --- Glossary CRUD ---

    async def create_glossary(self, glossary: Glossary) -> None:
        """Create a glossary record."""
        import json

        async with self.pool.acquire() as conn:
            # Convert entries to JSON
            entries_json = json.dumps(
                [
                    {
                        "term": entry.term,
                        "original_script": entry.original_script,
                        "definition": entry.definition,
                        "source": entry.source.value,
                        "occurrence_count": entry.occurrence_count,
                        "first_chapter": entry.first_chapter,
                        "needs_review": entry.needs_review,
                    }
                    for entry in glossary.entries
                ]
            )

            await conn.execute(
                """
                INSERT INTO glossaries (
                    id, book_id, entries, version, generated_at
                ) VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (book_id, version) DO UPDATE SET
                    entries = EXCLUDED.entries,
                    generated_at = EXCLUDED.generated_at
                """,
                glossary.id,
                glossary.book_id,
                entries_json,
                glossary.version,
                glossary.generated_at,
            )

    async def get_glossary_for_book(self, book_id: UUID) -> Glossary | None:
        """Get the glossary for a book."""
        import json

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM glossaries WHERE book_id = $1 ORDER BY version DESC LIMIT 1",
                book_id,
            )
            if not row:
                return None

            # Parse entries from JSON
            entries_data = json.loads(row["entries"]) if row["entries"] else []
            entries = [
                GlossaryEntry(
                    term=entry["term"],
                    original_script=entry["original_script"],
                    definition=entry["definition"],
                    source=TermSource(entry["source"]),
                    occurrence_count=entry["occurrence_count"],
                    first_chapter=entry.get("first_chapter"),
                    needs_review=entry.get("needs_review", False),
                )
                for entry in entries_data
            ]

            return Glossary(
                id=row["id"],
                book_id=row["book_id"],
                entries=entries,
                version=row["version"],
                generated_at=row["generated_at"],
            )

    # --- Manuscript CRUD ---

    async def create_manuscript(self, manuscript: Manuscript) -> None:
        """Create a manuscript record."""
        import json

        async with self.pool.acquire() as conn:
            # Convert chapters to JSON
            chapters_json = json.dumps(
                [
                    {
                        "number": chapter.number,
                        "title": chapter.title,
                        "content_html": chapter.content_html,
                    }
                    for chapter in manuscript.chapters
                ]
            )

            await conn.execute(
                """
                INSERT INTO manuscripts (
                    id, book_id, title, author, chapters, glossary_id,
                    table_of_contents, metadata, created_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                """,
                manuscript.id,
                manuscript.book_id,
                manuscript.title,
                manuscript.author,
                chapters_json,
                manuscript.glossary_id,
                json.dumps(manuscript.table_of_contents),
                json.dumps(manuscript.metadata),
                manuscript.created_at,
            )

    async def get_manuscript_for_book(self, book_id: UUID) -> Manuscript | None:
        """Get the manuscript for a book."""
        import json

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM manuscripts WHERE book_id = $1 ORDER BY created_at DESC LIMIT 1",
                book_id,
            )
            if not row:
                return None

            # Parse chapters from JSON
            chapters_data = json.loads(row["chapters"]) if row["chapters"] else []
            chapters = [
                Chapter(
                    number=chapter["number"],
                    title=chapter["title"],
                    content_html=chapter["content_html"],
                )
                for chapter in chapters_data
            ]

            # Parse table of contents
            toc = json.loads(row["table_of_contents"]) if row["table_of_contents"] else []

            # Parse metadata
            metadata = json.loads(row["metadata"]) if row["metadata"] else {}

            return Manuscript(
                id=row["id"],
                book_id=row["book_id"],
                title=row["title"],
                author=row["author"],
                chapters=chapters,
                glossary_id=row["glossary_id"],
                table_of_contents=toc,
                metadata=metadata,
                created_at=row["created_at"],
            )

    # --- Book Costs ---

    async def ensure_book_costs_table(self) -> None:
        """Create the book_costs table if it doesn't exist."""
        await self.execute(
            """
            CREATE TABLE IF NOT EXISTS book_costs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                book_id UUID NOT NULL,
                service TEXT NOT NULL,
                metric TEXT NOT NULL,
                quantity BIGINT NOT NULL,
                estimated_cost_usd NUMERIC(10, 6),
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
            """
        )

    async def save_book_costs(
        self, book_id: UUID, rows: list[tuple[str, str, int, float]]
    ) -> None:
        """Persist cost breakdown rows for a book.

        Args:
            book_id: The book these costs belong to.
            rows: List of (service, metric, quantity, estimated_cost_usd).
        """
        await self.execute_many(
            """
            INSERT INTO book_costs (book_id, service, metric, quantity, estimated_cost_usd)
            VALUES ($1, $2, $3, $4, $5)
            """,
            [(book_id, svc, metric, qty, cost) for svc, metric, qty, cost in rows],
        )

    async def get_book_costs(self, book_id: UUID) -> list[dict]:
        """Retrieve cost rows for a book."""
        rows = await self.fetch_many(
            "SELECT service, metric, quantity, estimated_cost_usd, created_at "
            "FROM book_costs WHERE book_id = $1 ORDER BY created_at",
            book_id,
        )
        return [
            {
                "service": r["service"],
                "metric": r["metric"],
                "quantity": r["quantity"],
                "estimated_cost_usd": float(r["estimated_cost_usd"]),
                "created_at": r["created_at"],
            }
            for r in rows
        ]

