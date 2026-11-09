"""Geospatial endpoints — municipal grain only.

GeoJSON is served directly from PostGIS. There is deliberately no tile server:
Benguet has 13 municipalities, so pg_tileserv/Martin/GeoServer would add an
operational surface for a problem this project does not have. If feature counts
ever exceed roughly 10,000, swap ST_AsGeoJSON for ST_AsMVT here. No other part
of the architecture changes.

There is no farm-parcel endpoint because no public farm-parcel layer exists for
Benguet. Rendering invented boundaries would be the exact failure the
micro-component was designed to avoid.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Query

from app import db

router = APIRouter(prefix="/geo", tags=["geo"])

# Tolerance in degrees. ~0.0001 deg is roughly 11 m at this latitude: enough
# to cut payload size without visibly moving a municipal boundary.
DEFAULT_TOLERANCE = 0.0001

# Benguet's PSGC code. The province digits sit in positions 3-5 of the ten-digit
# code, so this is 1401100000 - never 1411000000 assembled from region+province.
BENGUET_PSGC = "1401100000"


@router.get("/municipalities")
def municipalities(
    province_code: str = Query(BENGUET_PSGC, description="PSGC province code; Benguet by default"),
    tolerance: float = Query(DEFAULT_TOLERANCE, ge=0.0, le=0.01),
    commodity: str | None = Query(None, description="Join a value for choropleth shading"),
    variable: str = Query("farmgate_price"),
    period: str | None = Query(None, description="ISO date of the period to shade by"),
) -> dict:
    """Municipal polygons, optionally carrying one value per feature."""
    sql = """
        SELECT m.psgc_code, m.name, m.province_name, m.psgc_vintage, m.source_note,
               ST_AsGeoJSON(ST_SimplifyPreserveTopology(m.geom, :tol))::json AS geometry,
               v.value, v.unit, v.quality_flag, v.series_id, v.period_start
        FROM municipality m
        LEFT JOIN LATERAL (
            SELECT o.original_value AS value, s.unit, o.quality_flag, o.period_start, s.series_id
            FROM series s
            JOIN observation o ON o.series_id = s.series_id
            -- "Latest" must mean latest PUBLISHED. The panel runs to 2026-12 but
            -- the final months are not yet released, so ordering by period alone
            -- would shade every polygon as no-data.
            WHERE o.original_value IS NOT NULL AND o.quality_flag <> 'suspect'
            -- PSA publishes farmgate prices at PROVINCE grain, so a province
            -- series legitimately shades every municipality in that province.
            -- The response says so in metadata.grain; it is not a municipal
            -- measurement and must not be presented as one.
              AND s.geography_code IN (m.psgc_code, m.province_code)
              AND s.variable = :variable
              -- Casts are explicit: PostgreSQL cannot infer a parameter's type
              -- from `NULL OR col ILIKE $n` and errors out without them.
              AND (CAST(:commodity AS TEXT) IS NULL OR s.commodity ILIKE CAST(:commodity AS TEXT))
              AND (CAST(:period AS DATE) IS NULL OR o.period_start = CAST(:period AS DATE))
            ORDER BY o.period_start DESC
            LIMIT 1
        ) v ON TRUE
        WHERE m.province_code = :province
        ORDER BY m.name
    """
    try:
        found = db.rows(
            sql, tol=tolerance, province=province_code,
            variable=variable, commodity=commodity, period=period,
        )
    except Exception as exc:
        raise HTTPException(503, f"database unavailable: {exc}") from exc

    features = [
        {
            "type": "Feature",
            "id": r["psgc_code"],
            "geometry": r["geometry"] if isinstance(r["geometry"], dict) else json.loads(r["geometry"]),
            "properties": {
                "psgc_code": r["psgc_code"],
                "name": r["name"],
                "province": r["province_name"],
                "value": float(r["value"]) if r["value"] is not None else None,
                "unit": r["unit"],
                "quality_flag": r["quality_flag"],
                "series_id": r["series_id"],
                "period": str(r["period_start"]) if r["period_start"] else None,
                "has_data": r["value"] is not None,
            },
        }
        for r in found
    ]
    vintage = found[0]["psgc_vintage"] if found else None
    return {
        "type": "FeatureCollection",
        "features": features,
        "metadata": {
            "grain": "province value rendered on municipal polygons",
            "grain_warning": (
                "PSA publishes farmgate prices at province level. Every municipality in a "
                "province therefore carries the same value: this is one provincial "
                "observation drawn on municipal shapes, not municipal measurement."
            ),
            "psgc_vintage": str(vintage) if vintage else None,
            "boundary_source": (
                "faeldon/philippines-json-maps (MIT), municities-provdist-1401100000, "
                "PSGC 2026-3q; upstream altcoder/philippines-psgc-shapefiles, OCHA. "
                "Already EPSG:4326 - not reprojected."
            ),
            "note": (
                "Municipal grain is the finest geography PSA publishes for these series. "
                "Farm-level polygons are not shown because no public layer exists."
            ),
            "n_without_data": sum(1 for f in features if not f["properties"]["has_data"]),
        },
    }


@router.get("/sites")
def sites() -> dict:
    """Trading posts, facilities and (later) consented farms.

    Exact farm coordinates are restricted by the ethics commitment, so
    restricted points are returned at coarsened precision only.
    """
    try:
        found = db.rows(
            """
            SELECT site_id, site_type, label, psgc_code, precision_m, restricted,
                   ST_X(geom) AS lon, ST_Y(geom) AS lat
            FROM site_point
            WHERE restricted = FALSE
            ORDER BY site_type, label
            """
        )
    except Exception as exc:
        raise HTTPException(503, f"database unavailable: {exc}") from exc
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": r["site_id"],
                "geometry": {"type": "Point", "coordinates": [r["lon"], r["lat"]]},
                "properties": {k: r[k] for k in ("site_type", "label", "psgc_code", "precision_m")},
            }
            for r in found
        ],
        "metadata": {
            "note": "Restricted points are withheld entirely, not blurred client-side.",
            "empty_is_expected": True,
        },
    }
