"""Health, provenance and the standing disclosure the prototype must carry."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app import db
from app.auth import CurrentUser, current_user
from app.config import settings
from app.services.attribution import LICENCE_URL, SOURCE_URL

router = APIRouter(tags=["meta"])

PROTOTYPE_NOTICE = {
    "status": "historical research prototype",
    "observations_through": "2025-12-31",
    "banner": (
        "Historical research prototype — observations through 2025. "
        "Forecast panels show retrospective test dates only."
    ),
    "not_provided": [
        "No buy, sell or harvest-now advice.",
        "No live or future price advisory.",
        "No farm-level or parcel-level boundaries.",
        "No claim of national or CAR-wide representativeness.",
    ],
}


@router.get("/health")
def health() -> dict:
    ok, detail = db.healthy()
    return {
        "api": "ok",
        "database": "ok" if ok else "unavailable",
        "database_detail": detail,
        "study_cutoff": settings.study_cutoff,
    }


@router.get("/notice")
def notice() -> dict:
    """Served to the frontend so the banner text has one source of truth."""
    return PROTOTYPE_NOTICE


@router.get("/provenance")
def provenance(_: CurrentUser = Depends(current_user)) -> dict:
    """Every extract behind the curated layer, with checksums."""
    try:
        extracts = db.rows(
            """
            SELECT extract_id, source_table, source_table_title, source_url,
                   retrieved_at, reference_period, release_date, vintage,
                   raw_checksum, permitted_use, source_attribution
            FROM source_extract
            ORDER BY retrieved_at DESC
            """
        )
    except Exception as exc:
        raise HTTPException(503, f"database unavailable: {exc}") from exc
    return {
        "licence": "CC BY 4.0",
        "licence_url": LICENCE_URL,
        "source": SOURCE_URL,
        "count": len(extracts),
        "extracts": extracts,
        "vintage_warning": (
            "A 2026 retrieval may contain revised historical values. These data do not "
            "reproduce what an analyst knew in 2015 or 2020. Reference date and "
            "retrieval date are recorded separately."
        ),
    }
