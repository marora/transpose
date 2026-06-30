"""Admin dashboard API — issue #99.

Provides `/admin/api/*` JSON endpoints that power the per-book operations
dashboard at `/admin/`. Sits behind the Entra middleware Tank shipped
(`transpose.api.auth.entra_middleware`, scope `api://transpose-admin/Dashboard.Read`).

Phase 1a scope (this module):
- GET /admin/api/books              — list of books with cost / wall-time / validation summary
- GET /admin/api/books/{book_id}    — full per-book detail (stages + gates + cost breakdown)

Phase 1b (Oracle dependency):
- Quality column / score endpoint. Until Oracle ships
  `oracle-translation-quality-score-v1.md`, the `quality` field is a stub
  with `available: false` and a `reason`.

Data sources (Phase 1a):
- `books`               — book metadata, status, created_at, updated_at, page_count
- `book_costs`          — per-service spend (openai / doc_intelligence / blob_storage)
- `book_validation_reports` — append-only JSONB validation reports (latest per book)

When #97 (`book_cost_events`) lands, the per-stage cost + wall-time rollups
swap source — the response shape does NOT change.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from aiohttp import web

logger = logging.getLogger(__name__)

# The full set of pipeline stages (must match `STAGE_ORDER` in runner.py).
STAGE_ORDER: list[str] = [
    "ingest",
    "ocr",
    "chunk",
    "translate",
    "glossary",
    "assemble",
    "export",
    "audiobook",
    "workspace",
]

# The full set of quality gates the dashboard MUST surface (per Niobe brief).
# Each gate's `surfaces_after` is the pipeline stage it conceptually follows.
GATE_CATALOG: list[dict[str, str]] = [
    {"name": "operational_readiness", "surfaces_after": "preflight"},
    {"name": "ocr_sanity", "surfaces_after": "ocr"},
    {"name": "translation_completeness", "surfaces_after": "translate"},
    {"name": "glossary_integrity", "surfaces_after": "glossary"},
    {"name": "document_structure", "surfaces_after": "assemble"},
    {"name": "artifact_availability", "surfaces_after": "export"},
    {"name": "export_rendering", "surfaces_after": "export"},
    {"name": "golden_targeted_qa", "surfaces_after": "export"},
    {"name": "production_readiness", "surfaces_after": "export"},
    {"name": "source_output_comparison", "surfaces_after": "export"},
    {"name": "audio_quality", "surfaces_after": "audiobook"},
]

# Map cost rows (service, metric) → pipeline stage. Until #97 lands we cannot
# distinguish translate vs glossary OpenAI spend — both fall under `translate`
# and `glossary` is reported with `cost_usd: 0` plus a note. This is the only
# fidelity gap in Phase 1a; the API shape is forward-compatible with #97.
_COST_SERVICE_TO_STAGE: dict[str, str] = {
    "openai": "translate",
    "doc_intelligence": "ocr",
    "blob_storage": "export",
}


def _book_to_dict(row: Any) -> dict:
    return {
        "id": str(row["id"]),
        "title": row["title"],
        "author": row["author"],
        "source_language": row["source_language"],
        "status": row["status"],
        "page_count": row["page_count"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
    }


def _wall_time_seconds(row: Any) -> float | None:
    """Approximate wall-time for a run using book timestamps.

    Until #97 cost_events lands, per-stage wall time is unavailable; the
    only wall-time we can compute reliably is total = updated_at - created_at.
    Returns None when timestamps are missing.
    """
    created = row["created_at"]
    updated = row["updated_at"]
    if not created or not updated:
        return None
    delta = (updated - created).total_seconds()
    if delta < 0:
        return None
    return round(delta, 2)


def _rollup_costs(cost_rows: list[dict]) -> dict[str, Any]:
    """Aggregate book_costs rows into a per-stage cost breakdown."""
    by_stage: dict[str, float] = {stage: 0.0 for stage in STAGE_ORDER}
    by_service: dict[str, float] = {}
    raw: list[dict] = []
    for r in cost_rows:
        service = r["service"]
        metric = r["metric"]
        cost = float(r.get("estimated_cost_usd") or 0.0)
        stage = _COST_SERVICE_TO_STAGE.get(service)
        if stage:
            by_stage[stage] = round(by_stage[stage] + cost, 6)
        by_service[service] = round(by_service.get(service, 0.0) + cost, 6)
        raw.append({
            "service": service,
            "metric": metric,
            "quantity": int(r.get("quantity") or 0),
            "cost_usd": round(cost, 6),
        })
    total = round(sum(by_service.values()), 6)
    return {
        "total_usd": total,
        "by_stage": by_stage,
        "by_service": by_service,
        "rows": raw,
    }


def _summarize_gates(report: dict | None) -> dict[str, Any]:
    """Summarize a validation report into pass/fail counts + per-gate list."""
    if not report:
        return {
            "available": False,
            "overall": None,
            "total": len(GATE_CATALOG),
            "passed": 0,
            "failed": 0,
            "not_run": len(GATE_CATALOG),
            "total_duration_ms": 0.0,
            "gates": [
                {
                    "name": g["name"],
                    "surfaces_after": g["surfaces_after"],
                    "status": "not_run",
                    "passed": None,
                    "duration_ms": None,
                    "failure_reason": None,
                    "details": {},
                }
                for g in GATE_CATALOG
            ],
        }

    by_name = {g["name"]: g for g in (report.get("gates") or [])}
    gates_out: list[dict[str, Any]] = []
    passed_count = 0
    failed_count = 0
    not_run_count = 0
    total_duration = 0.0
    for entry in GATE_CATALOG:
        gname = entry["name"]
        rec = by_name.get(gname)
        if rec is None:
            status = "not_run"
            not_run_count += 1
            gates_out.append({
                "name": gname,
                "surfaces_after": entry["surfaces_after"],
                "status": status,
                "passed": None,
                "duration_ms": None,
                "failure_reason": None,
                "details": {},
            })
            continue
        passed = bool(rec.get("passed"))
        status = "passed" if passed else "failed"
        if passed:
            passed_count += 1
        else:
            failed_count += 1
        dur = rec.get("duration_ms")
        if isinstance(dur, (int, float)):
            total_duration += float(dur)
        failures = rec.get("failures") or []
        gates_out.append({
            "name": gname,
            "surfaces_after": entry["surfaces_after"],
            "status": status,
            "passed": passed,
            "duration_ms": dur,
            "failure_reason": "; ".join(failures) if failures else None,
            "details": rec.get("details") or {},
        })
    return {
        "available": True,
        "overall": report.get("overall"),
        "total": len(GATE_CATALOG),
        "passed": passed_count,
        "failed": failed_count,
        "not_run": not_run_count,
        "total_duration_ms": round(total_duration, 2),
        "gates": gates_out,
    }


_QUALITY_DECOMP_KEYS: tuple[tuple[str, str], ...] = (
    ("fluency", "Fluency"),
    ("cultural_register", "Cultural register"),
    ("terminology_nuance", "Terminology nuance"),
)


def _quality_band(score: int) -> str:
    """Map a 0–100 composite score to a green/amber/red tier (issue #109)."""
    if score >= 85:
        return "green"
    if score >= 65:
        return "amber"
    return "red"


def _build_quality(report: dict | None, book_id: str) -> dict[str, Any]:
    """Build the dashboard quality payload from a validation report.

    Reads `report["oracle_score"]` (populated by Trinity's Layer C judge, #104)
    and renders composite score + color band + decomposition. Null-safe: when
    `oracle_score` is missing, returns `available=False` so the frontend hides
    the column without breaking older runs.
    """
    oracle = report.get("oracle_score") if report else None
    if not oracle:
        return {
            "available": False,
            "score": None,
            "band": None,
            "reason": "Oracle Layer C has not run for this book yet.",
            "decomposition": [],
            "sampled_chunk_ids": [],
            "book_id": book_id,
        }
    score = oracle.get("composite_score")
    if not isinstance(score, (int, float)):
        return {
            "available": False,
            "score": None,
            "band": None,
            "reason": "Oracle score payload missing composite_score.",
            "decomposition": [],
            "sampled_chunk_ids": [],
            "book_id": book_id,
        }
    score = int(score)
    decomposition = [
        {"key": key, "label": label, "score": int(oracle[key])}
        for key, label in _QUALITY_DECOMP_KEYS
        if isinstance(oracle.get(key), (int, float))
    ]
    return {
        "available": True,
        "score": score,
        "band": _quality_band(score),
        "reason": None,
        "decomposition": decomposition,
        "sampled_chunk_ids": list(oracle.get("sampled_chunk_ids") or []),
        "book_id": book_id,
    }


def _validation_summary_label(summary: dict[str, Any]) -> str:
    if not summary.get("available"):
        return "—"
    total = summary["total"]
    passed = summary["passed"]
    failed = summary["failed"]
    if failed == 0:
        return f"✅ {passed}/{total} passed"
    return f"❌ {failed}/{total} failed"


async def _db_required(request: web.Request) -> Any:
    """Resolve the shared Database instance, or raise 503."""
    db = request.app.get("dashboard_db")
    if db is not None:
        return db
    # Fall back to the JobTracker's ServiceContext.
    job_tracker = request.app.get("job_tracker")
    ctx = getattr(job_tracker, "_ctx", None) if job_tracker is not None else None
    if ctx is not None and getattr(ctx, "db", None) is not None:
        return ctx.db
    raise web.HTTPServiceUnavailable(
        reason="Dashboard database not configured",
    )


async def _fetch_books(db) -> list[dict]:
    async with db.pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, title, author, source_language, status,
                   page_count, created_at, updated_at
            FROM books
            ORDER BY created_at DESC
            """
        )
    return [dict(r) for r in rows]


async def _fetch_costs_for_book(db, book_id: UUID) -> list[dict]:
    async with db.pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT service, metric, quantity, estimated_cost_usd, created_at
            FROM book_costs
            WHERE book_id = $1
            ORDER BY created_at
            """,
            book_id,
        )
    return [dict(r) for r in rows]


async def list_books(request: web.Request) -> web.Response:
    """GET /admin/api/books — one row per book, summary columns only."""
    db = await _db_required(request)
    rows = await _fetch_books(db)

    out: list[dict[str, Any]] = []
    for r in rows:
        book = _book_to_dict(r)
        bid = UUID(book["id"])
        cost_rows = await _fetch_costs_for_book(db, bid)
        cost = _rollup_costs(cost_rows)
        try:
            report = await db.get_latest_validation_report(bid)
        except Exception as exc:
            logger.warning("Failed to fetch validation report for %s: %s", bid, exc)
            report = None
        validation = _summarize_gates(report)
        out.append({
            **book,
            "wall_time_seconds": _wall_time_seconds(r),
            "cost": {
                "total_usd": cost["total_usd"],
                "by_stage": cost["by_stage"],
            },
            "validation": {
                "available": validation["available"],
                "overall": validation["overall"],
                "passed": validation["passed"],
                "failed": validation["failed"],
                "total": validation["total"],
                "label": _validation_summary_label(validation),
            },
            "quality": _build_quality(report, book["id"]),
        })
    return web.json_response({"books": out, "count": len(out)})


async def get_book_detail(request: web.Request) -> web.Response:
    """GET /admin/api/books/{book_id} — full per-book breakdown."""
    raw_id = request.match_info["book_id"]
    try:
        bid = UUID(raw_id)
    except ValueError:
        return web.json_response(
            {"error": {"code": "INVALID_BOOK_ID", "message": "book_id must be a UUID"}},
            status=400,
        )

    db = await _db_required(request)
    async with db.pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, title, author, source_language, status,
                   page_count, created_at, updated_at
            FROM books WHERE id = $1
            """,
            bid,
        )
    if not row:
        return web.json_response(
            {"error": {"code": "NOT_FOUND", "message": f"Book {raw_id} not found"}},
            status=404,
        )

    book = _book_to_dict(row)
    cost_rows = await _fetch_costs_for_book(db, bid)
    cost = _rollup_costs(cost_rows)
    try:
        report = await db.get_latest_validation_report(bid)
    except Exception as exc:
        logger.warning("Failed to fetch validation report for %s: %s", bid, exc)
        report = None
    validation = _summarize_gates(report)

    # Stage breakdown (8 stages + a validation row + a total row).
    # Per-stage wall_time_seconds is unavailable until #97 — emit `null`.
    stages: list[dict[str, Any]] = []
    for stage in STAGE_ORDER:
        cost_for_stage = cost["by_stage"].get(stage, 0.0)
        note: str | None = None
        if stage == "translate":
            note = "Includes glossary OpenAI spend until #97 (cost_events) lands."
        if stage == "glossary":
            note = "OpenAI spend rolled under 'translate' until #97 lands."
        stages.append({
            "name": stage,
            "cost_usd": cost_for_stage,
            "wall_time_seconds": None,
            "note": note,
        })

    # Validation row — total gate execution time across the run.
    stages.append({
        "name": "validation",
        "cost_usd": 0.0,
        "wall_time_seconds": (
            round(validation["total_duration_ms"] / 1000.0, 3)
            if validation["available"] else None
        ),
        "note": "Sum of all gate durations (from validation report).",
        "is_summary": True,
    })

    total_wall = _wall_time_seconds(row)
    stages.append({
        "name": "total",
        "cost_usd": cost["total_usd"],
        "wall_time_seconds": total_wall,
        "note": "Total = book updated_at - created_at (approximation until #97).",
        "is_total": True,
    })

    detail = {
        **book,
        "wall_time_seconds": total_wall,
        "stages": stages,
        "cost": cost,
        "validation": {
            **validation,
            "label": _validation_summary_label(validation),
        },
        "quality": _build_quality(report, book["id"]),
    }
    return web.json_response(detail)


# ---------------------------------------------------------------------------
# #99 endpoints backed by book_cost_events (#97)
# ---------------------------------------------------------------------------


async def _fetch_cost_events(db, book_id: UUID) -> list[dict]:
    async with db.pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, book_id, run_id, stage_name, started_at, ended_at,
                   input_tokens, output_tokens, ocr_pages,
                   blob_read_ops, blob_write_ops, estimated_cost_usd,
                   retries, status, error_message
            FROM book_cost_events
            WHERE book_id = $1
            ORDER BY started_at ASC
            """,
            book_id,
        )
    return [dict(r) for r in rows]


def _event_to_dict(ev: dict) -> dict[str, Any]:
    started = ev.get("started_at")
    ended = ev.get("ended_at")
    duration = (
        (ended - started).total_seconds()
        if (started and ended) else None
    )
    return {
        "id": str(ev["id"]),
        "book_id": str(ev["book_id"]),
        "run_id": str(ev["run_id"]),
        "stage_name": ev["stage_name"],
        "started_at": started.isoformat() if started else None,
        "ended_at": ended.isoformat() if ended else None,
        "duration_seconds": round(duration, 3) if duration is not None else None,
        "input_tokens": int(ev["input_tokens"]),
        "output_tokens": int(ev["output_tokens"]),
        "ocr_pages": int(ev["ocr_pages"]),
        "blob_read_ops": int(ev["blob_read_ops"]),
        "blob_write_ops": int(ev["blob_write_ops"]),
        "estimated_cost_usd": float(ev["estimated_cost_usd"]),
        "retries": int(ev["retries"]),
        "status": ev["status"],
        "error_message": ev.get("error_message"),
    }


def _rollup_stage_events(events: list[dict]) -> list[dict[str, Any]]:
    """Collapse all events for a book into one row per stage (sum across runs)."""
    by_stage: dict[str, dict[str, Any]] = {}
    for ev in events:
        bucket = by_stage.setdefault(
            ev["stage_name"],
            {
                "stage_name": ev["stage_name"],
                "run_count": 0,
                "completed_count": 0,
                "failed_count": 0,
                "started_count": 0,
                "duration_seconds": 0.0,
                "input_tokens": 0,
                "output_tokens": 0,
                "ocr_pages": 0,
                "blob_read_ops": 0,
                "blob_write_ops": 0,
                "estimated_cost_usd": 0.0,
                "retries": 0,
                "last_status": None,
                "last_started_at": None,
                "last_ended_at": None,
                "last_error_message": None,
            },
        )
        bucket["run_count"] += 1
        status = ev["status"]
        if status == "completed":
            bucket["completed_count"] += 1
        elif status == "failed":
            bucket["failed_count"] += 1
        else:
            bucket["started_count"] += 1
        started = ev.get("started_at")
        ended = ev.get("ended_at")
        if started and ended:
            bucket["duration_seconds"] += (ended - started).total_seconds()
        bucket["input_tokens"] += int(ev["input_tokens"])
        bucket["output_tokens"] += int(ev["output_tokens"])
        bucket["ocr_pages"] += int(ev["ocr_pages"])
        bucket["blob_read_ops"] += int(ev["blob_read_ops"])
        bucket["blob_write_ops"] += int(ev["blob_write_ops"])
        bucket["estimated_cost_usd"] += float(ev["estimated_cost_usd"])
        bucket["retries"] += int(ev["retries"])
        bucket["last_status"] = status
        bucket["last_started_at"] = started.isoformat() if started else None
        bucket["last_ended_at"] = ended.isoformat() if ended else None
        bucket["last_error_message"] = ev.get("error_message")

    # Preserve canonical stage ordering, then append any unknown stage names.
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for canonical in STAGE_ORDER:
        if canonical in by_stage:
            row = by_stage[canonical]
            row["duration_seconds"] = round(row["duration_seconds"], 3)
            row["estimated_cost_usd"] = round(row["estimated_cost_usd"], 6)
            out.append(row)
            seen.add(canonical)
    for stage_name, row in by_stage.items():
        if stage_name in seen:
            continue
        row["duration_seconds"] = round(row["duration_seconds"], 3)
        row["estimated_cost_usd"] = round(row["estimated_cost_usd"], 6)
        out.append(row)
    return out


async def get_book_stages(request: web.Request) -> web.Response:
    """GET /admin/api/books/{book_id}/stages — per-stage rollup from book_cost_events."""
    raw_id = request.match_info["book_id"]
    try:
        bid = UUID(raw_id)
    except ValueError:
        return web.json_response(
            {"error": {"code": "INVALID_BOOK_ID", "message": "book_id must be a UUID"}},
            status=400,
        )
    db = await _db_required(request)
    try:
        events = await _fetch_cost_events(db, bid)
    except Exception as exc:
        logger.warning("Failed to fetch cost events for %s: %s", bid, exc)
        events = []
    return web.json_response({
        "book_id": str(bid),
        "stages": _rollup_stage_events(events),
        "event_count": len(events),
    })


async def get_book_events(request: web.Request) -> web.Response:
    """GET /admin/api/books/{book_id}/events — raw cost event audit trail."""
    raw_id = request.match_info["book_id"]
    try:
        bid = UUID(raw_id)
    except ValueError:
        return web.json_response(
            {"error": {"code": "INVALID_BOOK_ID", "message": "book_id must be a UUID"}},
            status=400,
        )
    db = await _db_required(request)
    try:
        events = await _fetch_cost_events(db, bid)
    except Exception as exc:
        logger.warning("Failed to fetch cost events for %s: %s", bid, exc)
        events = []
    return web.json_response({
        "book_id": str(bid),
        "events": [_event_to_dict(ev) for ev in events],
        "count": len(events),
    })


async def _fetch_recent_completed_book_pages(
    db, *, limit: int
) -> dict[str, int]:
    """Return {book_id: page_count} for the N most recent EXPORTED books."""
    async with db.pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, page_count
            FROM books
            WHERE status = 'EXPORTED' AND page_count IS NOT NULL AND page_count > 0
            ORDER BY updated_at DESC
            LIMIT $1
            """,
            limit,
        )
    return {str(r["id"]): int(r["page_count"]) for r in rows}


async def _fetch_stage_totals_for_books(
    db, book_ids: list[UUID]
) -> dict[tuple[str, str], dict[str, float]]:
    """Return {(book_id_str, stage): {cost_usd, duration_seconds}} from book_cost_events."""
    if not book_ids:
        return {}
    async with db.pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT book_id, stage_name,
                   SUM(estimated_cost_usd) AS cost_usd,
                   SUM(
                       EXTRACT(EPOCH FROM (ended_at - started_at))
                   ) AS duration_seconds
            FROM book_cost_events
            WHERE book_id = ANY($1::uuid[])
              AND status = 'completed'
              AND ended_at IS NOT NULL
            GROUP BY book_id, stage_name
            """,
            book_ids,
        )
    return {
        (str(r["book_id"]), r["stage_name"]): {
            "cost_usd": float(r["cost_usd"] or 0.0),
            "duration_seconds": float(r["duration_seconds"] or 0.0),
        }
        for r in rows
    }


async def get_projection(request: web.Request) -> web.Response:
    """GET /admin/api/projection?pages=N — estimate cost + time for an N-page book."""
    from transpose.observability.projector import StagePerBookSample, estimate

    raw_pages = request.query.get("pages", "")
    try:
        pages = int(raw_pages)
        if pages <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return web.json_response(
            {"error": {"code": "INVALID_PAGES", "message": "pages must be a positive integer"}},
            status=400,
        )

    db = await _db_required(request)
    rolling_window = 3
    try:
        pages_by_book = await _fetch_recent_completed_book_pages(db, limit=rolling_window)
        book_uuids = [UUID(b) for b in pages_by_book]
        totals = await _fetch_stage_totals_for_books(db, book_uuids)
    except Exception as exc:
        logger.warning("Failed to gather projection inputs: %s", exc)
        pages_by_book = {}
        totals = {}

    samples = [
        StagePerBookSample(
            book_id=book_id,
            stage_name=stage,
            cost_usd=vals["cost_usd"],
            duration_seconds=vals["duration_seconds"],
            pages=pages_by_book[book_id],
        )
        for (book_id, stage), vals in totals.items()
        if book_id in pages_by_book
    ]

    result = estimate(samples, pages=pages, rolling_window=rolling_window)
    return web.json_response({
        "pages": result.pages,
        "confidence": result.confidence,
        "sample_book_count": result.sample_book_count,
        "total_cost_usd": result.total_cost_usd,
        "total_duration_seconds": result.total_duration_seconds,
        "stages": [
            {
                "stage_name": s.stage_name,
                "estimated_cost_usd": s.estimated_cost_usd,
                "estimated_duration_seconds": s.estimated_duration_seconds,
                "sample_size": s.sample_size,
            }
            for s in result.stages
        ],
    })


def register_dashboard_routes(app: web.Application) -> None:
    """Attach `/admin/api/*` dashboard routes to an aiohttp app.

    Called from `transpose.api.create_app`. The Entra middleware already
    protects every `/admin/*` path, so no extra auth wiring is required here.
    """
    app.router.add_get("/admin/api/books", list_books)
    app.router.add_get("/admin/api/projection", get_projection)
    app.router.add_get("/admin/api/books/{book_id}", get_book_detail)
    app.router.add_get("/admin/api/books/{book_id}/stages", get_book_stages)
    app.router.add_get("/admin/api/books/{book_id}/events", get_book_events)
