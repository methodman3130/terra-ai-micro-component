"""Series and observation endpoints.

Quality flags are returned, never filtered out. A client that wants to hide
imputed points may do so; the API will not make that decision silently.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app import db
from app.services.attribution import STANDARD_MODIFICATIONS, render

router = APIRouter(prefix="/series", tags=["series"])

_SERIES_SQL = """
SELECT s.series_id, s.commodity, s.variable, s.geography_code, s.geography_name,
       s.geography_level, s.frequency, s.unit, s.grade_variety,
       s.frozen_at IS NOT NULL AS frozen,
       e.source_table, e.source_table_title, e.retrieved_at, e.permitted_use
FROM series s
JOIN source_extract e ON e.extract_id = s.extract_id
"""


@router.get("")
def list_series(
    commodity: str | None = Query(None),
    variable: str | None = Query(None),
    geography_code: str | None = Query(None),
    frozen_only: bool = Query(False, description="Only series frozen for scoring"),
) -> dict:
    clauses, params = [], {}
    if commodity:
        clauses.append("s.commodity ILIKE :commodity")
        params["commodity"] = commodity
    if variable:
        clauses.append("s.variable = :variable")
        params["variable"] = variable
    if geography_code:
        clauses.append("s.geography_code = :geography_code")
        params["geography_code"] = geography_code
    if frozen_only:
        clauses.append("s.frozen_at IS NOT NULL")
    sql = _SERIES_SQL + ("WHERE " + " AND ".join(clauses) if clauses else "") + " ORDER BY s.series_id"
    try:
        found = db.rows(sql, **params)
    except Exception as exc:
        raise HTTPException(503, f"database unavailable: {exc}") from exc
    return {"count": len(found), "series": found}


@router.get("/{series_id}/observations")
def observations(series_id: str, include_imputed: bool = Query(True)) -> dict:
    try:
        meta = db.one(_SERIES_SQL + "WHERE s.series_id = :sid", sid=series_id)
    except Exception as exc:
        raise HTTPException(503, f"database unavailable: {exc}") from exc
    if meta is None:
        raise HTTPException(404, f"series {series_id!r} not found")

    sql = """
        SELECT period_start, period_end, original_value, curated_value,
               missing_reason, quality_flag, rule_id
        FROM observation
        WHERE series_id = :sid
    """
    if not include_imputed:
        sql += " AND quality_flag <> 'imputed'"
    sql += " ORDER BY period_start"
    points = db.rows(sql, sid=series_id)

    attribution = render(
        table=meta["source_table"],
        title=meta["source_table_title"],
        retrieved=str(meta["retrieved_at"]),
        modifications=STANDARD_MODIFICATIONS,
    )
    flagged = sum(1 for p in points if p["quality_flag"] != "ok")
    return {
        "series": meta,
        "observations": points,
        "quality": {
            "n": len(points),
            "n_flagged": flagged,
            "n_missing": sum(1 for p in points if p["original_value"] is None),
            "note": "Denominators are stated. Flagged points are returned, not removed.",
        },
        "attribution": attribution.as_dict(),
    }
