"""Health, provenance and the standing disclosure the prototype must carry."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app import db
from app.auth import CurrentUser, current_user
from app.config import settings
from app.services.attribution import LICENCE_URL, SOURCE_URL

# Public archive of code, derived data, checksums, protocol and benchmark records.
# Replace with the minted DOI once the deposit is made.
REPRODUCIBILITY_URL = "https://github.com/methodman3130/terra-ai-micro-component"

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


# ---------------------------------------------------------------------------
# Public reporting surface.
#
# These two endpoints are deliberately open. The research data they describe is
# already public and CC BY 4.0, and a prototype that asserts reproducibility
# while hiding its own provenance behind a login is asserting it to nobody. The
# authenticated panel still gates the curated series themselves; what is open
# here is the account of where those series came from and what they can bear.
# ---------------------------------------------------------------------------

CLEANING_RULES = [
    {
        "rule_id": "R1",
        "trigger": "Period published blank by the source agency",
        "action": "Stored as NULL with missing_reason 'absent'",
        "never": "Not imputed, not interpolated, not coerced to zero",
    },
    {
        "rule_id": "R2",
        "trigger": "Period published as 0.00",
        "action": "Original value retained as published, quality_flag set to 'suspect'",
        "never": "Excluded from forecast targets and from lag features; not deleted",
    },
]

STUDY_DESIGN = {
    "frequency": "monthly",
    "geography_published": "province",
    "geography_rendered": "municipality",
    "geography_warning": (
        "Farmgate prices are published by the source agency at province level. The map "
        "renders one provincial value across every municipal polygon. These are not "
        "municipal measurements and no municipal or farm-level claim can be drawn from them."
    ),
    "observation_window": "2010-01 to 2026-12",
    "scoring_cutoff": "2025-12-31",
    "horizons_assessed": [1, 3],
    "primary_horizon": 1,
    "minimum_training_observations": {"general": 60, "AutoARIMA_monthly": 96},
    "acceptance_rule": (
        "A predictive claim required the candidate to reduce paired mean absolute error "
        "by at least 10 per cent against BOTH the random walk and the seasonal naive, "
        "with MASE below 1 where defined, at the one-step horizon, over at least 24 "
        "common target dates. Fixed before scoring and applied in code."
    ),
    "verdict": "REVISE",
    "verdict_meaning": (
        "No candidate met the acceptance rule at the registered horizon on any "
        "pre-registered commodity. Descriptive results are retained; predictive scope "
        "is revised. This prototype issues no forecasts."
    ),
}


@router.get("/methods")
def methods() -> dict:
    """Open account of retrieval, licensing, cleaning and evaluation design."""
    try:
        extracts = db.rows(
            """
            SELECT source_table, source_table_title, source_url, retrieved_at,
                   reference_period, vintage, raw_checksum, permitted_use
            FROM source_extract
            ORDER BY source_table
            """
        )
        runs = db.rows(
            "SELECT rule_id, script_version, rows_affected, rationale, ran_at "
            "FROM cleaning_run ORDER BY ran_at, rule_id"
        )
    except Exception as exc:
        raise HTTPException(503, f"database unavailable: {exc}") from exc

    return {
        "status": PROTOTYPE_NOTICE["status"],
        "licence": "CC BY 4.0",
        "licence_url": LICENCE_URL,
        "source": SOURCE_URL,
        "attribution_note": (
            "Data from the Philippine Statistics Authority OpenSTAT portal, licensed "
            "CC BY 4.0, modified by the University of the Cordilleras as recorded per "
            "extract. PSA does not endorse this use."
        ),
        "extracts": extracts,
        "cleaning_rules": CLEANING_RULES,
        "cleaning_runs": runs,
        "design": STUDY_DESIGN,
        "vintage_warning": (
            "A 2026 retrieval may contain values revised since original publication. "
            "These data do not reproduce the information set available to an analyst "
            "in an earlier year. Reference period and retrieval date are stored separately."
        ),
        "reproducibility": {
            "note": (
                "Each raw API response is stored with its SHA-256 checksum, permitting "
                "byte-exact verification of re-retrieval."
            ),
            "repository": REPRODUCIBILITY_URL,
        },
    }


@router.get("/fitness")
def fitness() -> dict:
    """Per-series coverage and whether the protocol permits a forecast claim.

    'forecast_permitted' is answered from the record, not from optimism: a series
    qualifies only if it has enough scoreable observations to train under the
    protocol AND a scored candidate met the acceptance rule at the primary
    horizon. At the time of writing no series qualifies, which is the finding.
    """
    try:
        rows = db.rows(
            """
            SELECT s.series_id, s.commodity, s.unit, s.frequency,
                   s.geography_name, s.geography_level,
                   count(o.*)                                        AS slots,
                   count(o.original_value)                           AS published,
                   count(*) FILTER (WHERE o.quality_flag = 'suspect') AS flagged_zero,
                   count(*) FILTER (WHERE o.missing_reason IS NOT NULL) AS absent,
                   count(*) FILTER (WHERE o.original_value IS NOT NULL
                                      AND o.quality_flag = 'ok')      AS scoreable,
                   max(o.period_start) FILTER (WHERE o.original_value IS NOT NULL
                                      AND o.quality_flag = 'ok')      AS latest_valid_period
            FROM series s
            LEFT JOIN observation o ON o.series_id = s.series_id
            GROUP BY s.series_id, s.commodity, s.unit, s.frequency,
                     s.geography_name, s.geography_level
            ORDER BY s.commodity
            """
        )
        passes = db.rows(
            """
            SELECT series_id, model, horizon, mase,
                   skill_vs_random_walk AS rw, skill_vs_seasonal_naive AS sn
            FROM benchmark_score
            WHERE horizon = 1
              AND model NOT IN ('RandomWalk', 'SeasonalNaive')
              AND mase < 1
              AND skill_vs_random_walk >= 0.10
              AND skill_vs_seasonal_naive >= 0.10
            """
        )
    except Exception as exc:
        raise HTTPException(503, f"database unavailable: {exc}") from exc

    qualifying = {p["series_id"]: p for p in passes}
    MIN_TRAIN = 60

    out = []
    for r in rows:
        scoreable = r["scoreable"] or 0
        trainable = scoreable >= MIN_TRAIN
        hit = qualifying.get(r["series_id"])
        if not trainable:
            reason = (
                f"Not scoreable: {scoreable} usable observations against a "
                f"{MIN_TRAIN}-observation minimum training window."
            )
        elif hit is None:
            reason = (
                "Scored, but no candidate met the pre-registered acceptance rule at the "
                "one-month horizon. No forecast is offered for this series."
            )
        else:
            reason = (
                f"{hit['model']} met the acceptance rule nominally at h=1. This was not a "
                "pre-registered commodity and the result is uncorrected for multiple "
                "comparisons; it is a hypothesis for prospective testing, not a validated "
                "forecast."
            )
        out.append({
            **{k: r[k] for k in (
                "series_id", "commodity", "unit", "frequency",
                "geography_name", "geography_level")},
            "slots": r["slots"],
            "published": r["published"],
            "flagged_zero": r["flagged_zero"],
            "absent": r["absent"],
            "scoreable": scoreable,
            "latest_valid_period": str(r["latest_valid_period"]) if r["latest_valid_period"] else None,
            "trainable": trainable,
            "forecast_permitted": False,
            "nominal_pass_at_h1": hit is not None,
            "status_reason": reason,
        })

    return {
        "min_training_observations": MIN_TRAIN,
        "primary_horizon": 1,
        "series": out,
        "n_series": len(out),
        "n_trainable": sum(1 for x in out if x["trainable"]),
        "n_forecast_permitted": 0,
        "note": (
            "forecast_permitted is false for every series. The prototype displays "
            "retrospective back-test scores against two naive baselines and issues no "
            "point forecasts, advisories or recommendations."
        ),
    }
