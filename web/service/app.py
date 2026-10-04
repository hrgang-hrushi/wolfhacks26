"""The read-only data service in front of the Tiger Data database.

Run:   web/.venv/bin/uvicorn web.service.app:app --host 0.0.0.0 --port 8000 --workers 1
Needs: TIGER_DATABASE_URL (environment, or data/raw/tiger.env). Optional: TIGER_SCHEMA, ALLOWED_ORIGINS (comma-separated).
Docs:  /docs lists every route and lets you try it.

Rules:
- GET only. Every connection is read-only, in UTC, with a time limit on connecting and on each query.
- Every data route reads the load record and runs its query inside one read-only snapshot, and answers "loading"
  unless the latest load is complete, so a reply never mixes two loads.
- Blank is null. A non-finite number is null.
- A database failure is a 503 with a fixed message. The driver's own text (host, port, user) never reaches a reply
  or a log line.
"""
import json
import logging
import math
import os
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal

import psycopg
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from psycopg_pool import ConnectionPool, PoolClosed, PoolTimeout

from web.service import queries
from web.tiger import config, export

RISK_PAGE = 5000
LOGGERS = ("psycopg.pool", "psycopg")


@dataclass
class Settings:
    url: str | None = None                 # None: read TIGER_DATABASE_URL when the service starts
    schema: str | None = None              # None: TIGER_SCHEMA or 'unwatched'
    connect_timeout: int = 5
    pool_wait: float = 5.0
    statement_timeout_ms: int = 8000
    lock_timeout_ms: int = 3000
    allowed_origins: list | None = None    # None: ALLOWED_ORIGINS, else any site (never with credentials)


class Loading(Exception):
    def __init__(self, status):
        self.status = status


class ScrubFilter(logging.Filter):
    """The pool's workers log failed connections with the driver's text, which names the host, port and user."""

    def filter(self, record):
        if record.levelno >= logging.WARNING:
            kind = config.classify(record.exc_info[1]) if record.exc_info and record.exc_info[1] else "unavailable"
            text = record.getMessage().lower()
            if kind == "unavailable":
                kind = "network" if any(h in text for h in config._NETWORK_HINTS) else (
                    "login" if any(h in text for h in config._LOGIN_HINTS) else "unavailable")
            record.msg, record.args, record.exc_info, record.exc_text = f"database connection problem: {config.MESSAGES[kind]}", (), None, None
        return True


def install_log_filter():
    for name in LOGGERS:
        logger = logging.getLogger(name)
        if not any(isinstance(f, ScrubFilter) for f in logger.filters):
            logger.addFilter(ScrubFilter())


def clean(value):
    """Plain JSON values: blank and non-finite numbers are null, times are ISO 8601 in UTC with a Z."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Decimal):
        return clean(float(value)) if value.is_finite() else None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [clean(v) for v in value]
    return str(value)


def respond(data, status=200):
    return Response(content=json.dumps(clean(data), allow_nan=False, separators=(",", ":")), status_code=status,
                    media_type="application/json")


def _origins(settings):
    if settings.allowed_origins is not None:
        return settings.allowed_origins
    raw = os.environ.get("ALLOWED_ORIGINS", "").strip()
    return [o.strip() for o in raw.split(",") if o.strip()] or ["*"]


def make_pool(settings):
    """A small pool, built closed and opened without waiting, so the service starts even when the database is down."""
    url = settings.url or config.database_url()            # a missing setting stops the start and names the key
    schema = settings.schema or config.schema_name()

    def configure(conn):
        config.apply_session(conn, schema=schema, read_only=True, statement_timeout_ms=settings.statement_timeout_ms,
                             lock_timeout_ms=settings.lock_timeout_ms)
        conn.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
        conn.read_only = True

    pool = ConnectionPool(url, min_size=1, max_size=4, timeout=settings.pool_wait,
                          kwargs={"connect_timeout": settings.connect_timeout}, configure=configure, open=False,
                          name="dashboard")
    pool.open(wait=False)
    return pool, schema


def create_app(pool=None, *, clock=None, settings=None):
    settings = settings or Settings()
    clock = clock or (lambda: datetime.now(timezone.utc))
    install_log_filter()

    @asynccontextmanager
    async def lifespan(app):
        if pool is not None:
            app.state.pool, app.state.schema, owned = pool, settings.schema or config.schema_name(), False
        else:
            app.state.pool, app.state.schema = make_pool(settings)
            owned = True
        try:
            yield
        finally:
            if owned:
                app.state.pool.close()

    app = FastAPI(title="Unwatched Roads data service", lifespan=lifespan,
                  description="Read-only service over the Tiger Data database: the repair work list, road details, "
                              "flood alerts, database statistics and the risk-file download.")
    app.add_middleware(CORSMiddleware, allow_origins=_origins(settings), allow_credentials=False, allow_methods=["GET"],
                       allow_headers=[])

    @contextmanager
    def reading(guard=True):
        """One connection, one read-only snapshot. With `guard`, refuses unless the latest load is complete."""
        with app.state.pool.connection(timeout=settings.pool_wait) as conn:
            if guard:
                _, status = queries.manifest_status(conn)
                if status != "complete":
                    raise Loading(status)
            yield conn

    def unavailable(kind="unavailable"):
        return respond({"error": "database unavailable", "kind": kind, "detail": config.MESSAGES[kind]}, 503)

    @app.exception_handler(Loading)
    async def _loading(request: Request, exc: Loading):
        return respond({"error": "loading", "load_status": exc.status,
                        "detail": "a load is in progress or has not finished; try again shortly"}, 503)

    @app.exception_handler(queries.BadRequest)
    async def _bad(request: Request, exc: queries.BadRequest):
        return respond({"error": str(exc)}, 400)

    @app.exception_handler(queries.NotFound)
    async def _missing(request: Request, exc: queries.NotFound):
        return respond({"error": str(exc)}, 404)

    @app.exception_handler(psycopg.Error)
    async def _db(request: Request, exc: psycopg.Error):
        if isinstance(exc, psycopg.errors.LockNotAvailable):      # a load is copying: it holds the tables until it commits
            return await _loading(request, Loading("a load is copying"))
        return unavailable(config.classify(exc))

    @app.exception_handler(PoolTimeout)
    async def _pool(request: Request, exc: PoolTimeout):
        return unavailable("unavailable")

    @app.exception_handler(PoolClosed)
    async def _closed(request: Request, exc: PoolClosed):
        return unavailable("unavailable")

    @app.exception_handler(config.DatabaseUnavailable)
    async def _down(request: Request, exc: config.DatabaseUnavailable):
        return unavailable(exc.kind)

    @app.get("/api/health")
    def health():
        with reading(guard=False) as conn:
            _, status = queries.manifest_status(conn)
        return respond({"ok": True, "database": "ok", "load_status": status, "time": clock()})

    @app.get("/api/summary")
    def summary():
        with reading(guard=False) as conn:
            return respond(queries.summary(conn))

    @app.get("/api/worklist")
    def worklist(bucket: str | None = None, county: str | None = None, system: str | None = None, in_zone: bool | None = None,
                 sort: str = "rank", direction: str = "asc", limit: int = 50, offset: int = 0):
        with reading() as conn:
            return respond(queries.worklist(conn, bucket=bucket, county=county, system=system, in_zone=in_zone, sort=sort,
                                            direction=direction, limit=limit, offset=offset))

    @app.get("/api/road")
    def road(seg_id: str = ""):
        if not queries.SEG_ID.match(seg_id):
            raise queries.BadRequest("seg_id must look like ncdot:40002748092:0.940")
        with reading() as conn:
            return respond(queries.road(conn, seg_id))

    @app.get("/api/alerts")
    def alerts(as_of: str | None = None, hours: int = 2):
        when = queries.parse_time(as_of) if as_of else None
        if hours not in (1, 2):
            raise queries.BadRequest("hours must be 1 or 2")
        with reading() as conn:
            return respond(queries.alerts(conn, when, clock(), hours))

    @app.get("/api/alerts/peaks")
    def alert_peaks(limit: int = 10):
        with reading() as conn:
            return respond(queries.alert_peaks(conn, limit))

    @app.get("/api/camera_history")
    def camera_history(camera_id: str = "", start: str | None = None, end: str | None = None):
        if not camera_id:
            raise queries.BadRequest("camera_id is required")
        lo = queries.parse_time(start, "start") if start else None
        hi = queries.parse_time(end, "end") if end else None
        with reading() as conn:
            return respond(queries.camera_history(conn, camera_id, lo, hi))

    @app.get("/api/stats")
    def stats():
        with reading(guard=False) as conn:
            return respond(queries.stats(conn, app.state.schema))

    def risk_pages():
        """The risk file's rows, a page at a time. Each page is its own short checkout, so no connection is held while
        the client reads. Every page checks it still belongs to the same complete load; otherwise the stream stops."""
        after, load_id = "", None
        while True:
            with app.state.pool.connection(timeout=settings.pool_wait) as conn:
                current, status = queries.manifest_status(conn)
                if status != "complete":
                    raise Loading(status)
                if load_id is None:
                    load_id = current
                elif current != load_id:
                    raise Loading("replaced by a newer load during the download")
                rows = queries.risk_page(conn, after, RISK_PAGE)
            if not rows:
                return
            yield from rows
            after = rows[-1][0]

    app.state.risk_pages = risk_pages

    @app.get("/api/export/risk.csv")
    def risk_csv():
        chunks = export.iter_risk_csv(risk_pages())
        first = next(chunks)                       # the first page is read before any header is sent: a failure here is a 503

        def body():
            yield first
            yield from chunks
        return StreamingResponse(body(), media_type="text/csv; charset=utf-8",
                                 headers={"Content-Disposition": f'attachment; filename="{export.FILE_NAME}"'})

    @app.get("/api/export/dictionary")
    def risk_dictionary():
        return respond(export.dictionary())

    return app


app = create_app()
