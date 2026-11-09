"""Benchmark endpoints.

Scores are read back exactly as the harness wrote them: by commodity,
geography, frequency and horizon, never pooled across units or frequencies.

The ``interpretation`` block is part of the response on purpose. A MASE below 1
compares against the declared training scaling quantity; it does not by itself
demonstrate superiority over both out-of-sample naive forecasts. The API states
that next to the number rather than leaving a reader to infer a win.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app import db
from app.forecasting.harness import DECLARED_BOX, seasonal_naive_is_independent

router = APIRouter(prefix="/benchmark", tags=["benchmark"])

BASELINE_MODELS = ("RandomWalk", "SeasonalNaive")


def _beats_all_baselines(found: list[dict]) -> list[str]:
    """Candidates that beat every baseline AT THEIR OWN HORIZON, on MAE.

    Baselines must be matched within a horizon. Keying them by model name alone
    would let a candidate at h=1 be judged against a baseline at h=3 — a longer,
    harder task — and would manufacture false wins.
    """
    baselines: dict[int, list[dict]] = {}
    for r in found:
        if r["model"] in BASELINE_MODELS and r.get("mae") is not None:
            baselines.setdefault(r["horizon"], []).append(r)

    winners = []
    for r in found:
        if r["model"] in BASELINE_MODELS or r.get("mae") is None:
            continue
        peers = baselines.get(r["horizon"], [])
        if peers and all(r["mae"] < b["mae"] for b in peers):
            winners.append(f"{r['model']}@h{r['horizon']}")
    return winners



@router.get("/protocol")
def protocol() -> dict:
    """The declared parameter box and what it means."""
    return {
        "declared_box": DECLARED_BOX.as_dict(),
        "mandatory_comparators": ["RandomWalk", "SeasonalNaive (only where m > 1)"],
        "candidates": ["AutoETS", "AutoARIMA"],
        "notes": [
            "AutoARIMA runs inside the declared box, not on library defaults. "
            "Leaving defaults on would void the preregistration.",
            "On an annual series m = 1, so seasonal naive duplicates the random walk "
            "and is not reported as an independent second baseline.",
            "Targets are original observations only. Imputed values are never scored.",
        ],
    }


@router.get("/{series_id}")
def scores(series_id: str, horizon: int | None = Query(None)) -> dict:
    sql = """
        SELECT b.model, b.horizon, b.n_origins, b.mase, b.mae, b.rmse, b.bias,
               b.engine, b.scored_at, p.label AS protocol, p.declared_box,
               s.frequency, s.unit, s.commodity, s.geography_name
        FROM benchmark_score b
        JOIN benchmark_protocol p ON p.protocol_id = b.protocol_id
        JOIN series s ON s.series_id = b.series_id
        WHERE b.series_id = :sid
    """
    params: dict = {"sid": series_id}
    if horizon is not None:
        sql += " AND b.horizon = :h"
        params["h"] = horizon
    sql += " ORDER BY b.horizon, b.model, b.engine"

    try:
        found = db.rows(sql, **params)
    except Exception as exc:
        raise HTTPException(503, f"database unavailable: {exc}") from exc
    if not found:
        raise HTTPException(404, f"no scores recorded for series {series_id!r}")

    frequency = found[0]["frequency"]
    season_length = {"monthly": 12, "quarterly": 4}.get(frequency, 1)

    beats_all = _beats_all_baselines(found)

    # Disagreement between engines scoring the same model is reportable.
    by_key: dict[tuple, set] = {}
    for r in found:
        by_key.setdefault((r["model"], r["horizon"]), set()).add(r["engine"])
    cross_checked = [f"{m}@h{h}" for (m, h), engines in by_key.items() if len(engines) > 1]

    return {
        "series_id": series_id,
        "frequency": frequency,
        "scores": found,
        "interpretation": {
            "mase_caveat": (
                "MASE below 1 compares errors against the declared training scaling "
                "quantity. It does not by itself demonstrate superiority over both "
                "out-of-sample naive forecasts; paired comparator errors remain necessary."
            ),
            "beats_all_baselines_on_mae": beats_all,
            "seasonal_naive_independent": seasonal_naive_is_independent(season_length),
            "cross_checked_models": cross_checked,
            "bias_sign": "e = forecast - actual; positive mean error indicates overforecasting.",
            "pooling": "Scores are not pooled across commodity, unit, frequency or horizon.",
        },
    }
