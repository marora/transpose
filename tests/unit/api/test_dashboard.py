"""Unit tests for the dashboard API (issue #99).

Tests cover:
- Pure helpers (`_rollup_costs`, `_summarize_gates`, `_wall_time_seconds`).
- Endpoint behaviour with a fake Database injected via `app["dashboard_db"]`.
- Auth integration: endpoints sit behind Tank's Entra middleware.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest

from transpose.api.dashboard import (
    GATE_CATALOG,
    STAGE_ORDER,
    _rollup_costs,
    _summarize_gates,
    _validation_summary_label,
    _wall_time_seconds,
)

# ── Helper tests ────────────────────────────────────────────────────


def test_rollup_costs_maps_services_to_stages():
    rows = [
        {"service": "openai", "metric": "input_tokens",
         "quantity": 1000, "estimated_cost_usd": 0.5},
        {"service": "openai", "metric": "output_tokens",
         "quantity": 200, "estimated_cost_usd": 0.4},
        {"service": "doc_intelligence", "metric": "pages",
         "quantity": 50, "estimated_cost_usd": 0.75},
        {"service": "blob_storage", "metric": "write_operations",
         "quantity": 30, "estimated_cost_usd": 0.001},
    ]
    out = _rollup_costs(rows)
    assert out["by_stage"]["translate"] == pytest.approx(0.9, abs=1e-6)
    assert out["by_stage"]["ocr"] == pytest.approx(0.75, abs=1e-6)
    assert out["by_stage"]["export"] == pytest.approx(0.001, abs=1e-6)
    # Stages with no spend remain at 0.0.
    assert out["by_stage"]["ingest"] == 0.0
    assert out["by_stage"]["chunk"] == 0.0
    assert out["total_usd"] == pytest.approx(1.651, abs=1e-6)
    assert len(out["rows"]) == 4


def test_rollup_costs_empty():
    out = _rollup_costs([])
    assert out["total_usd"] == 0.0
    assert all(v == 0.0 for v in out["by_stage"].values())
    assert out["rows"] == []
    assert set(out["by_stage"].keys()) == set(STAGE_ORDER)


def test_summarize_gates_no_report():
    s = _summarize_gates(None)
    assert s["available"] is False
    assert s["total"] == len(GATE_CATALOG)
    assert s["passed"] == 0
    assert s["failed"] == 0
    assert s["not_run"] == len(GATE_CATALOG)
    assert {g["name"] for g in s["gates"]} == {g["name"] for g in GATE_CATALOG}
    assert all(g["status"] == "not_run" for g in s["gates"])


def test_summarize_gates_full_pass():
    report = {
        "overall": "PASS",
        "gates": [
            {"name": g["name"], "passed": True, "failures": [], "details": {}, "duration_ms": 12.5}
            for g in GATE_CATALOG
        ],
    }
    s = _summarize_gates(report)
    assert s["available"] is True
    assert s["overall"] == "PASS"
    assert s["passed"] == len(GATE_CATALOG)
    assert s["failed"] == 0
    assert s["not_run"] == 0
    assert s["total_duration_ms"] == pytest.approx(12.5 * len(GATE_CATALOG), abs=1e-2)
    assert _validation_summary_label(s) == f"✅ {len(GATE_CATALOG)}/{len(GATE_CATALOG)} passed"


def test_summarize_gates_partial_fail_surfaces_failure_reason():
    report = {
        "overall": "FAIL",
        "gates": [
            {
                "name": "ocr_sanity",
                "passed": False,
                "failures": ["confidence too low"],
                "details": {"avg": 0.3},
                "duration_ms": 8.1,
            },
            {
                "name": "translation_completeness",
                "passed": True,
                "failures": [],
                "details": {},
                "duration_ms": 4.0,
            },
        ],
    }
    s = _summarize_gates(report)
    assert s["available"] is True
    assert s["overall"] == "FAIL"
    assert s["passed"] == 1
    assert s["failed"] == 1
    assert s["not_run"] == len(GATE_CATALOG) - 2
    by_name = {g["name"]: g for g in s["gates"]}
    assert by_name["ocr_sanity"]["status"] == "failed"
    assert by_name["ocr_sanity"]["failure_reason"] == "confidence too low"
    assert by_name["translation_completeness"]["status"] == "passed"
    assert by_name["operational_readiness"]["status"] == "not_run"
    assert _validation_summary_label(s).startswith("❌ 1/")


def test_wall_time_seconds_basic():
    created = datetime(2026, 5, 22, 10, 0, 0, tzinfo=UTC)
    updated = created + timedelta(minutes=42, seconds=13)
    row = {"created_at": created, "updated_at": updated}
    assert _wall_time_seconds(row) == pytest.approx(42 * 60 + 13, abs=0.01)


def test_wall_time_seconds_handles_missing():
    assert _wall_time_seconds({"created_at": None, "updated_at": None}) is None


# ── Endpoint tests ──────────────────────────────────────────────────

TENANT_ID = "48af2a40-dd60-4e0d-ba42-f0fac9a31d93"
CLIENT_ID = "5ffe7826-3caa-41a8-9359-a5dd3aee4407"
AUDIENCE = "api://transpose-admin/Dashboard.Read"


class _FakePool:
    """Minimal asyncpg-pool stand-in returning canned rows."""

    def __init__(self, books, costs_by_book):
        self._books = books
        self._costs = costs_by_book

    def acquire(self):
        return _FakeAcquire(self)


class _FakeAcquire:
    def __init__(self, pool):
        self._pool = pool

    async def __aenter__(self):
        return _FakeConn(self._pool)

    async def __aexit__(self, *exc):
        return None


class _FakeConn:
    def __init__(self, pool):
        self._pool = pool

    async def fetch(self, query, *args):
        if "FROM books" in query:
            return [_RowProxy(b) for b in self._pool._books]
        if "FROM book_costs" in query:
            book_id = args[0]
            rows = self._pool._costs.get(book_id, [])
            return [_RowProxy(r) for r in rows]
        return []

    async def fetchrow(self, query, *args):
        if "FROM books WHERE id" in query:
            book_id = args[0]
            for b in self._pool._books:
                if b["id"] == book_id:
                    return _RowProxy(b)
            return None
        return None


class _RowProxy(dict):
    """Dict-style row that also supports `row["key"]` like asyncpg.Record."""


class _FakeDb:
    def __init__(self, books, costs_by_book, reports_by_book):
        self.pool = _FakePool(books, costs_by_book)
        self._reports = reports_by_book

    async def get_latest_validation_report(self, book_id: UUID):
        return self._reports.get(book_id)


@pytest.fixture
def admin_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENTRA_TENANT_ID", TENANT_ID)
    monkeypatch.setenv("ENTRA_ADMIN_CLIENT_ID", CLIENT_ID)
    monkeypatch.setenv("ENTRA_ADMIN_AUDIENCE", AUDIENCE)


def _build_valid_token():
    """Build a signed test JWT (mirrors test_entra_middleware helper)."""
    from datetime import datetime, timedelta

    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    jwk = jwt.algorithms.RSAAlgorithm.to_jwk(public_key, as_dict=True)
    jwk["kid"] = "dashboard-test-kid"
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "aud": "api://transpose-admin",
            "iss": f"https://login.microsoftonline.com/{TENANT_ID}/v2.0",
            "exp": now + timedelta(minutes=5),
            "nbf": now - timedelta(seconds=30),
            "iat": now - timedelta(seconds=30),
            "name": "Trinity Tester",
            "oid": "00000000-0000-0000-0000-000000000999",
            "scp": "Dashboard.Read",
            "tid": TENANT_ID,
        },
        key=private_key,
        algorithm="RS256",
        headers={"kid": "dashboard-test-kid"},
    )
    return token, jwk


async def _make_client(aiohttp_client, fake_db, fetch_json: AsyncMock):
    from transpose.api import create_app

    with patch("transpose.observability.tracing.configure_tracing"):
        app = create_app()
    if "entra_token_validator" in app:
        app["entra_token_validator"]._fetch_json = fetch_json
    app["dashboard_db"] = fake_db
    return await aiohttp_client(app)


def _sample_dataset():
    now = datetime(2026, 5, 21, 12, 0, 0, tzinfo=UTC)
    bid1 = uuid4()
    bid2 = uuid4()
    books = [
        {
            "id": bid1,
            "title": "Test Hindi Book",
            "author": "Anon",
            "source_language": "hindi",
            "status": "exported",
            "page_count": 240,
            "created_at": now,
            "updated_at": now + timedelta(minutes=37),
        },
        {
            "id": bid2,
            "title": "Failed Run",
            "author": None,
            "source_language": "punjabi",
            "status": "failed",
            "page_count": 120,
            "created_at": now,
            "updated_at": now + timedelta(minutes=12),
        },
    ]
    costs = {
        bid1: [
            {
                "service": "openai", "metric": "input_tokens",
                "quantity": 10000, "estimated_cost_usd": 1.0, "created_at": now,
            },
            {
                "service": "doc_intelligence", "metric": "pages",
                "quantity": 240, "estimated_cost_usd": 3.6, "created_at": now,
            },
        ],
        bid2: [],
    }
    reports = {
        bid1: {
            "overall": "PASS",
            "gates": [
                {
                    "name": g["name"], "passed": True, "failures": [],
                    "details": {}, "duration_ms": 5.0,
                }
                for g in GATE_CATALOG
            ],
        },
        bid2: {
            "overall": "FAIL",
            "gates": [
                {
                    "name": "ocr_sanity", "passed": False,
                    "failures": ["low confidence"], "details": {}, "duration_ms": 12.0,
                },
            ],
        },
    }
    return books, costs, reports, bid1, bid2


@pytest.mark.asyncio
async def test_list_books_requires_auth(admin_env, aiohttp_client) -> None:
    books, costs, reports, _, _ = _sample_dataset()
    fake_db = _FakeDb(books, costs, reports)
    client = await _make_client(aiohttp_client, fake_db, AsyncMock())

    res = await client.get("/admin/api/books")

    assert res.status == 401


@pytest.mark.asyncio
async def test_list_books_returns_summary(admin_env, aiohttp_client) -> None:
    token, jwk = _build_valid_token()
    books, costs, reports, bid1, bid2 = _sample_dataset()
    fake_db = _FakeDb(books, costs, reports)
    fetch_json = AsyncMock(
        side_effect=[
            {"issuer": f"https://login.microsoftonline.com/{TENANT_ID}/v2.0",
             "jwks_uri": f"https://login.microsoftonline.com/{TENANT_ID}/discovery/v2.0/keys"},
            {"keys": [jwk]},
        ]
    )
    client = await _make_client(aiohttp_client, fake_db, fetch_json)

    res = await client.get(
        "/admin/api/books",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert res.status == 200
    body = await res.json()
    assert body["count"] == 2
    assert len(body["books"]) == 2
    by_id = {b["id"]: b for b in body["books"]}
    b1 = by_id[str(bid1)]
    assert b1["title"] == "Test Hindi Book"
    assert b1["cost"]["total_usd"] == pytest.approx(4.6, abs=1e-6)
    # Stage rollup: openai → translate, doc_intelligence → ocr.
    assert b1["cost"]["by_stage"]["translate"] == pytest.approx(1.0, abs=1e-6)
    assert b1["cost"]["by_stage"]["ocr"] == pytest.approx(3.6, abs=1e-6)
    assert b1["wall_time_seconds"] == pytest.approx(37 * 60, abs=0.01)
    assert b1["validation"]["available"] is True
    assert b1["validation"]["passed"] == len(GATE_CATALOG)
    assert b1["validation"]["failed"] == 0
    assert b1["validation"]["label"].startswith("✅")
    # Quality must always be a stub in Phase 1a.
    assert b1["quality"]["available"] is False
    assert b1["quality"]["score"] is None

    b2 = by_id[str(bid2)]
    assert b2["validation"]["failed"] == 1
    assert b2["validation"]["label"].startswith("❌")
    assert b2["cost"]["total_usd"] == 0.0


@pytest.mark.asyncio
async def test_get_book_detail_returns_stages_and_gates(admin_env, aiohttp_client) -> None:
    token, jwk = _build_valid_token()
    books, costs, reports, bid1, _ = _sample_dataset()
    fake_db = _FakeDb(books, costs, reports)
    fetch_json = AsyncMock(
        side_effect=[
            {"issuer": f"https://login.microsoftonline.com/{TENANT_ID}/v2.0",
             "jwks_uri": f"https://login.microsoftonline.com/{TENANT_ID}/discovery/v2.0/keys"},
            {"keys": [jwk]},
        ]
    )
    client = await _make_client(aiohttp_client, fake_db, fetch_json)

    res = await client.get(
        f"/admin/api/books/{bid1}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert res.status == 200
    body = await res.json()
    # Stages = 8 pipeline stages + validation row + total row.
    stage_names = [s["name"] for s in body["stages"]]
    assert stage_names[: len(STAGE_ORDER)] == STAGE_ORDER
    assert "validation" in stage_names
    assert stage_names[-1] == "total"
    # Validation block surfaces every gate from the catalog.
    gate_names = {g["name"] for g in body["validation"]["gates"]}
    assert gate_names == {g["name"] for g in GATE_CATALOG}
    # Quality stub is in the detail payload.
    assert body["quality"]["available"] is False


@pytest.mark.asyncio
async def test_get_book_detail_bad_uuid(admin_env, aiohttp_client) -> None:
    token, jwk = _build_valid_token()
    books, costs, reports, _, _ = _sample_dataset()
    fake_db = _FakeDb(books, costs, reports)
    fetch_json = AsyncMock(
        side_effect=[
            {"issuer": f"https://login.microsoftonline.com/{TENANT_ID}/v2.0",
             "jwks_uri": f"https://login.microsoftonline.com/{TENANT_ID}/discovery/v2.0/keys"},
            {"keys": [jwk]},
        ]
    )
    client = await _make_client(aiohttp_client, fake_db, fetch_json)

    res = await client.get(
        "/admin/api/books/not-a-uuid",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert res.status == 400


@pytest.mark.asyncio
async def test_get_book_detail_not_found(admin_env, aiohttp_client) -> None:
    token, jwk = _build_valid_token()
    books, costs, reports, _, _ = _sample_dataset()
    fake_db = _FakeDb(books, costs, reports)
    fetch_json = AsyncMock(
        side_effect=[
            {"issuer": f"https://login.microsoftonline.com/{TENANT_ID}/v2.0",
             "jwks_uri": f"https://login.microsoftonline.com/{TENANT_ID}/discovery/v2.0/keys"},
            {"keys": [jwk]},
        ]
    )
    client = await _make_client(aiohttp_client, fake_db, fetch_json)

    res = await client.get(
        f"/admin/api/books/{uuid4()}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert res.status == 404
