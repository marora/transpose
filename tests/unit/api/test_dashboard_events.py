"""Endpoint tests for dashboard cost-event routes (#99 / #101).

Covers:
- GET /admin/api/books/{book_id}/stages
- GET /admin/api/books/{book_id}/events
- GET /admin/api/projection?pages=N
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest

from transpose.api.dashboard import (
    _event_to_dict,
    _rollup_stage_events,
)

TENANT_ID = "00000000-0000-0000-0000-000000000001"
CLIENT_ID = "00000000-0000-0000-0000-000000000002"
AUDIENCE = "api://transpose-admin"


# ---------- pure helper coverage ----------------------------------------------


def _ev(
    book_id: UUID,
    run_id: UUID,
    stage: str,
    *,
    started: datetime,
    ended: datetime | None,
    cost: float = 0.0,
    in_tok: int = 0,
    out_tok: int = 0,
    pages: int = 0,
    blob_r: int = 0,
    blob_w: int = 0,
    retries: int = 0,
    status: str = "completed",
    error: str | None = None,
) -> dict[str, Any]:
    return {
        "id": uuid4(),
        "book_id": book_id,
        "run_id": run_id,
        "stage_name": stage,
        "started_at": started,
        "ended_at": ended,
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "ocr_pages": pages,
        "blob_read_ops": blob_r,
        "blob_write_ops": blob_w,
        "estimated_cost_usd": cost,
        "retries": retries,
        "status": status,
        "error_message": error,
    }


def test_event_to_dict_serializes_timestamps_and_duration() -> None:
    book_id = uuid4()
    run_id = uuid4()
    started = datetime(2026, 5, 24, 12, 0, 0, tzinfo=UTC)
    ended = started + timedelta(seconds=42)
    ev = _ev(book_id, run_id, "translate", started=started, ended=ended, cost=0.5,
             in_tok=1000, out_tok=400)
    out = _event_to_dict(ev)
    assert out["book_id"] == str(book_id)
    assert out["run_id"] == str(run_id)
    assert out["stage_name"] == "translate"
    assert out["started_at"] == started.isoformat()
    assert out["ended_at"] == ended.isoformat()
    assert out["duration_seconds"] == 42.0
    assert out["input_tokens"] == 1000
    assert out["status"] == "completed"


def test_event_to_dict_handles_in_flight_event() -> None:
    started = datetime(2026, 5, 24, 12, 0, 0, tzinfo=UTC)
    ev = _ev(uuid4(), uuid4(), "ocr", started=started, ended=None,
             status="started")
    out = _event_to_dict(ev)
    assert out["ended_at"] is None
    assert out["duration_seconds"] is None
    assert out["status"] == "started"


def test_rollup_stage_events_orders_by_stage_order() -> None:
    book_id = uuid4()
    run_id = uuid4()
    base = datetime(2026, 5, 24, 12, 0, 0, tzinfo=UTC)
    events = [
        _ev(book_id, run_id, "translate", started=base + timedelta(seconds=5),
            ended=base + timedelta(seconds=65), cost=0.42, in_tok=200, out_tok=120),
        _ev(book_id, run_id, "ingest", started=base, ended=base + timedelta(seconds=5)),
        _ev(book_id, run_id, "ocr", started=base + timedelta(seconds=5),
            ended=base + timedelta(seconds=5), pages=240),
    ]
    rolled = _rollup_stage_events(events)
    names = [r["stage_name"] for r in rolled]
    assert names == ["ingest", "ocr", "translate"]
    translate = next(r for r in rolled if r["stage_name"] == "translate")
    assert translate["estimated_cost_usd"] == pytest.approx(0.42)
    assert translate["duration_seconds"] == pytest.approx(60.0)
    assert translate["input_tokens"] == 200


def test_rollup_stage_events_sums_across_runs_and_counts_status() -> None:
    book_id = uuid4()
    run_a = uuid4()
    run_b = uuid4()
    base = datetime(2026, 5, 24, 12, 0, 0, tzinfo=UTC)
    events = [
        _ev(book_id, run_a, "ocr", started=base,
            ended=base + timedelta(seconds=30), cost=0.5, status="failed",
            error="DI timeout"),
        _ev(book_id, run_b, "ocr", started=base + timedelta(minutes=5),
            ended=base + timedelta(minutes=5, seconds=20),
            cost=0.3, status="completed"),
        _ev(book_id, run_b, "translate", started=base + timedelta(minutes=6),
            ended=None, status="started"),
    ]
    rolled = _rollup_stage_events(events)
    ocr = next(r for r in rolled if r["stage_name"] == "ocr")
    assert ocr["run_count"] == 2
    assert ocr["failed_count"] == 1
    assert ocr["completed_count"] == 1
    assert ocr["duration_seconds"] == pytest.approx(50.0)
    assert ocr["estimated_cost_usd"] == pytest.approx(0.8)
    translate = next(r for r in rolled if r["stage_name"] == "translate")
    assert translate["started_count"] == 1
    assert translate["last_status"] == "started"
    assert translate["last_ended_at"] is None


# ---------- endpoint integration ----------------------------------------------


class _RowProxy(dict):
    pass


class _FakeConn:
    def __init__(self, *, books, events, exported_pages_by_id):
        self._books = books
        self._events = events
        self._exported_pages_by_id = exported_pages_by_id

    async def fetch(self, query, *args):
        if "FROM book_cost_events" in query and "SUM" in query:
            book_ids = args[0]
            buckets: dict[tuple[UUID, str], dict[str, float]] = {}
            for ev in self._events:
                if ev["book_id"] not in book_ids:
                    continue
                if ev["status"] != "completed" or ev["ended_at"] is None:
                    continue
                key = (ev["book_id"], ev["stage_name"])
                b = buckets.setdefault(key, {"cost_usd": 0.0, "duration_seconds": 0.0})
                b["cost_usd"] += float(ev["estimated_cost_usd"])
                b["duration_seconds"] += (ev["ended_at"] - ev["started_at"]).total_seconds()
            return [
                _RowProxy({
                    "book_id": bid, "stage_name": stage,
                    "cost_usd": vals["cost_usd"],
                    "duration_seconds": vals["duration_seconds"],
                })
                for (bid, stage), vals in buckets.items()
            ]
        if "FROM book_cost_events" in query:
            book_id = args[0]
            rows = [ev for ev in self._events if ev["book_id"] == book_id]
            rows.sort(key=lambda r: r["started_at"])
            return [_RowProxy(r) for r in rows]
        if "WHERE status = 'EXPORTED'" in query:
            return [
                _RowProxy({"id": bid, "page_count": pages})
                for bid, pages in self._exported_pages_by_id.items()
            ]
        if "FROM book_costs" in query:
            return []
        if "FROM books" in query:
            return [_RowProxy(b) for b in self._books]
        return []

    async def fetchrow(self, query, *args):
        if "FROM books WHERE id" in query:
            for b in self._books:
                if b["id"] == args[0]:
                    return _RowProxy(b)
        return None


class _FakeAcquire:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *exc):
        return None


class _FakePool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return _FakeAcquire(self._conn)


class _FakeDb:
    def __init__(self, *, books, events, exported_pages_by_id):
        conn = _FakeConn(
            books=books, events=events,
            exported_pages_by_id=exported_pages_by_id,
        )
        self.pool = _FakePool(conn)

    async def get_latest_validation_report(self, book_id):
        return None


@pytest.fixture
def admin_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENTRA_TENANT_ID", TENANT_ID)
    monkeypatch.setenv("ENTRA_ADMIN_CLIENT_ID", CLIENT_ID)
    monkeypatch.setenv("ENTRA_ADMIN_AUDIENCE", AUDIENCE)


def _build_valid_token():
    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    jwk = jwt.algorithms.RSAAlgorithm.to_jwk(public_key, as_dict=True)
    jwk["kid"] = "events-test-kid"
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "aud": AUDIENCE,
            "iss": f"https://login.microsoftonline.com/{TENANT_ID}/v2.0",
            "exp": now + timedelta(minutes=5),
            "nbf": now - timedelta(seconds=30),
            "iat": now - timedelta(seconds=30),
            "name": "Tester",
            "oid": "00000000-0000-0000-0000-000000000999",
            "scp": "Dashboard.Read",
            "tid": TENANT_ID,
        },
        key=private_key,
        algorithm="RS256",
        headers={"kid": "events-test-kid"},
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


@pytest.mark.asyncio
async def test_get_book_stages_returns_rollup(admin_env, aiohttp_client) -> None:
    token, jwk = _build_valid_token()
    book_id = uuid4()
    run_id = uuid4()
    base = datetime(2026, 5, 24, 12, 0, 0, tzinfo=UTC)
    events = [
        _ev(book_id, run_id, "ingest", started=base, ended=base + timedelta(seconds=3)),
        _ev(book_id, run_id, "translate", started=base + timedelta(seconds=5),
            ended=base + timedelta(seconds=65), cost=0.42, in_tok=200, out_tok=100),
    ]
    fake = _FakeDb(books=[], events=events, exported_pages_by_id={})
    fetch_json = AsyncMock(side_effect=[
        {"jwks_uri": "https://login.microsoftonline.com/x/discovery/keys"},
        {"keys": [jwk]},
    ])
    client = await _make_client(aiohttp_client, fake, fetch_json)

    resp = await client.get(
        f"/admin/api/books/{book_id}/stages",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status == 200
    body = await resp.json()
    assert body["book_id"] == str(book_id)
    assert body["event_count"] == 2
    stages_by_name = {s["stage_name"]: s for s in body["stages"]}
    assert "ingest" in stages_by_name and "translate" in stages_by_name
    assert stages_by_name["translate"]["estimated_cost_usd"] == pytest.approx(0.42)


@pytest.mark.asyncio
async def test_get_book_stages_requires_auth(admin_env, aiohttp_client) -> None:
    fake = _FakeDb(books=[], events=[], exported_pages_by_id={})
    client = await _make_client(aiohttp_client, fake, AsyncMock())
    resp = await client.get(f"/admin/api/books/{uuid4()}/stages")
    assert resp.status == 401


@pytest.mark.asyncio
async def test_get_book_stages_bad_uuid(admin_env, aiohttp_client) -> None:
    token, jwk = _build_valid_token()
    fake = _FakeDb(books=[], events=[], exported_pages_by_id={})
    fetch_json = AsyncMock(side_effect=[
        {"jwks_uri": "https://login.microsoftonline.com/x/discovery/keys"},
        {"keys": [jwk]},
    ])
    client = await _make_client(aiohttp_client, fake, fetch_json)
    resp = await client.get(
        "/admin/api/books/not-a-uuid/stages",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status == 400


@pytest.mark.asyncio
async def test_get_book_events_returns_raw_audit_trail(admin_env, aiohttp_client) -> None:
    token, jwk = _build_valid_token()
    book_id = uuid4()
    run_id = uuid4()
    base = datetime(2026, 5, 24, 12, 0, 0, tzinfo=UTC)
    events = [
        _ev(book_id, run_id, "translate", started=base,
            ended=base + timedelta(seconds=10), cost=0.1),
    ]
    fake = _FakeDb(books=[], events=events, exported_pages_by_id={})
    fetch_json = AsyncMock(side_effect=[
        {"jwks_uri": "https://login.microsoftonline.com/x/discovery/keys"},
        {"keys": [jwk]},
    ])
    client = await _make_client(aiohttp_client, fake, fetch_json)

    resp = await client.get(
        f"/admin/api/books/{book_id}/events",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status == 200
    body = await resp.json()
    assert body["count"] == 1
    assert body["events"][0]["stage_name"] == "translate"
    assert body["events"][0]["estimated_cost_usd"] == pytest.approx(0.1)


@pytest.mark.asyncio
async def test_projection_returns_estimate(admin_env, aiohttp_client) -> None:
    token, jwk = _build_valid_token()
    base = datetime(2026, 5, 24, 12, 0, 0, tzinfo=UTC)
    book_a, book_b = uuid4(), uuid4()
    run_a, run_b = uuid4(), uuid4()
    events = [
        _ev(book_a, run_a, "translate", started=base,
            ended=base + timedelta(seconds=600), cost=1.0),
        _ev(book_b, run_b, "translate", started=base,
            ended=base + timedelta(seconds=1200), cost=2.0),
    ]
    fake = _FakeDb(
        books=[],
        events=events,
        exported_pages_by_id={book_a: 100, book_b: 200},
    )
    fetch_json = AsyncMock(side_effect=[
        {"jwks_uri": "https://login.microsoftonline.com/x/discovery/keys"},
        {"keys": [jwk]},
    ])
    client = await _make_client(aiohttp_client, fake, fetch_json)

    resp = await client.get(
        "/admin/api/projection?pages=150",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status == 200
    body = await resp.json()
    assert body["pages"] == 150
    assert body["confidence"] == "medium"
    assert body["sample_book_count"] == 2
    # median(0.01, 0.01) = 0.01 → 0.01 × 150 = 1.5
    assert body["total_cost_usd"] == pytest.approx(1.5)


@pytest.mark.asyncio
async def test_projection_requires_auth(admin_env, aiohttp_client) -> None:
    fake = _FakeDb(books=[], events=[], exported_pages_by_id={})
    client = await _make_client(aiohttp_client, fake, AsyncMock())
    resp = await client.get("/admin/api/projection?pages=250")
    assert resp.status == 401


@pytest.mark.asyncio
async def test_projection_rejects_invalid_pages(admin_env, aiohttp_client) -> None:
    token, jwk = _build_valid_token()
    fake = _FakeDb(books=[], events=[], exported_pages_by_id={})
    fetch_json = AsyncMock(side_effect=[
        {"jwks_uri": "https://login.microsoftonline.com/x/discovery/keys"},
        {"keys": [jwk]},
    ])
    client = await _make_client(aiohttp_client, fake, fetch_json)

    resp = await client.get(
        "/admin/api/projection?pages=0",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status == 400

    resp = await client.get(
        "/admin/api/projection?pages=banana",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status == 400


@pytest.mark.asyncio
async def test_projection_empty_history_returns_none_confidence(
    admin_env, aiohttp_client
) -> None:
    token, jwk = _build_valid_token()
    fake = _FakeDb(books=[], events=[], exported_pages_by_id={})
    fetch_json = AsyncMock(side_effect=[
        {"jwks_uri": "https://login.microsoftonline.com/x/discovery/keys"},
        {"keys": [jwk]},
    ])
    client = await _make_client(aiohttp_client, fake, fetch_json)

    resp = await client.get(
        "/admin/api/projection?pages=250",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status == 200
    body = await resp.json()
    assert body["confidence"] == "none"
    assert body["sample_book_count"] == 0
    assert body["total_cost_usd"] == 0.0
