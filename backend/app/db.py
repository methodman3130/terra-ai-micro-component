"""Database access.

Deliberately thin: SQLAlchemy Core with explicit SQL, no ORM mapping layer.
The schema is the contract and it lives in db/001_schema.sql.

The engine is created lazily so the application can start, and report its own
unhealthy state, without a database present.
"""
from __future__ import annotations

import os
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.pool import NullPool

from app.config import settings

_engine: Engine | None = None


def get_engine() -> Engine:
    """Create the engine lazily, pooling according to where we are running.

    On a long-lived server a connection pool is what you want. On a serverless
    platform it is actively harmful: each function instance holds its own pool,
    instances scale out independently, and Postgres runs out of connections
    long before the platform runs out of concurrency. There the right shape is
    no pool at all, pointed at a connection pooler on the database side (on
    Neon, the ``-pooler`` host).

    Set TERRA_SERVERLESS=1 on Vercel, Cloud Run with concurrency 1, or any
    other platform that scales by process.
    """
    global _engine
    if _engine is None:
        serverless = os.environ.get("TERRA_SERVERLESS", "").lower() in {"1", "true", "yes"}
        kwargs: dict = {
            "future": True,
            "connect_args": {"application_name": "terra-mvp-api"},
        }
        if serverless:
            kwargs["poolclass"] = NullPool
        else:
            kwargs["pool_pre_ping"] = True
        _engine = create_engine(settings.database_url, **kwargs)
    return _engine


def healthy() -> tuple[bool, str]:
    try:
        with get_engine().connect() as conn:
            postgis = conn.execute(text("SELECT postgis_version()")).scalar_one()
        return True, f"postgis {postgis}"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def rows(sql: str, **params: Any) -> list[dict[str, Any]]:
    with get_engine().connect() as conn:
        result = conn.execute(text(sql), params)
        return [dict(r) for r in result.mappings()]


def one(sql: str, **params: Any) -> dict[str, Any] | None:
    found = rows(sql, **params)
    return found[0] if found else None
