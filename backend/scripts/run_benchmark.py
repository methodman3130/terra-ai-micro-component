"""Score every frozen series against the preregistered protocol and store results.

Usage:  python scripts/run_benchmark.py [--horizons 1 3 6] [--no-candidates]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, text

from app.config import settings
from app.forecasting import metrics
from app.forecasting.harness import DECLARED_BOX, min_train_for, run_protocol

SEASON_LENGTH = 12
MIN_TRAIN = 60  # the proposal's floor for monthly series
PROTOCOL_LABEL = "benguet-farmgate-monthly-v1"


def software_versions() -> dict[str, str]:
    import sklearn
    versions = {"python": sys.version.split()[0], "scikit-learn": sklearn.__version__}
    try:
        import statsforecast
        versions["statsforecast"] = statsforecast.__version__
    except ImportError:
        versions["statsforecast"] = "absent"
    return versions


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--horizons", type=int, nargs="+", default=[1, 3, 6])
    parser.add_argument("--no-candidates", action="store_true")
    parser.add_argument("--no-boosted", action="store_true")
    args = parser.parse_args()

    cutoff = date.fromisoformat(settings.study_cutoff)
    engine = create_engine(settings.database_url)

    with engine.begin() as conn:
        protocol_id = conn.execute(
            text("""
            INSERT INTO benchmark_protocol
              (label, declared_box, horizons, min_train, final_window_start,
               final_window_end, software_versions)
            VALUES (:l, CAST(:box AS JSONB), :h, :mt, DATE '2023-01-01', :fe,
                    CAST(:sv AS JSONB))
            ON CONFLICT (label) DO UPDATE SET software_versions = EXCLUDED.software_versions
            RETURNING protocol_id
            """),
            {
                "l": PROTOCOL_LABEL, "box": json.dumps(DECLARED_BOX.as_dict()),
                "h": args.horizons, "mt": MIN_TRAIN, "fe": cutoff,
                "sv": json.dumps(software_versions()),
            },
        ).scalar_one()

        series_ids = [
            r[0] for r in conn.execute(
                text("SELECT series_id FROM series WHERE frozen_at IS NOT NULL ORDER BY series_id")
            )
        ]

        for sid in series_ids:
            rows = conn.execute(
                text("""
                SELECT period_start, original_value, quality_flag
                FROM observation WHERE series_id = :s ORDER BY period_start
                """), {"s": sid},
            ).all()

            periods = [r[0] for r in rows]
            # Suspect points (published 0.00) are excluded as both target and
            # feature input: a zero farmgate price would drag a lag feature down
            # as surely as it would corrupt a score.
            values = [
                float(r[1]) if r[1] is not None and r[2] != "suspect" else None
                for r in rows
            ]

            runs = run_protocol(
                values, periods, horizons=args.horizons, min_train=MIN_TRAIN,
                season_length=SEASON_LENGTH, cutoff=cutoff,
                include_candidates=not args.no_candidates,
                include_boosted=not args.no_boosted,
                frequency="monthly",
            )

            # Baseline MAE per horizon, for relative skill. Computed first so
            # every candidate is compared against baselines at its OWN horizon.
            scored = {}
            for run in runs:
                if run.origins:
                    scored[(run.model, run.horizon)] = run.scores()

            baseline_mae = {
                (m, h): sc.mae for (m, h), sc in scored.items()
                if m in ("RandomWalk", "SeasonalNaive")
            }

            for run in runs:
                if not run.origins:
                    print(f"  {sid} {run.model} h={run.horizon}: no scored origins "
                          f"({len(run.skipped)} skipped)")
                    continue
                s = scored[(run.model, run.horizon)]
                rw = baseline_mae.get(("RandomWalk", run.horizon))
                sn = baseline_mae.get(("SeasonalNaive", run.horizon))
                skill_rw = metrics.relative_skill(s.mae, rw) if rw is not None else None
                skill_sn = metrics.relative_skill(s.mae, sn) if sn is not None else None
                conn.execute(
                    text("""
                    INSERT INTO benchmark_score
                      (protocol_id, series_id, model, horizon, n_origins,
                       mase, mae, rmse, bias, engine,
                       skill_vs_random_walk, skill_vs_seasonal_naive,
                       n_undefined_scale, min_train_used)
                    VALUES (:p,:s,:m,:h,:n,:mase,:mae,:rmse,:bias,:e,
                            :srw,:ssn,:nu,:mt)
                    ON CONFLICT (protocol_id, series_id, model, horizon, engine)
                    DO UPDATE SET n_origins=EXCLUDED.n_origins, mase=EXCLUDED.mase,
                                  mae=EXCLUDED.mae, rmse=EXCLUDED.rmse,
                                  bias=EXCLUDED.bias, scored_at=now(),
                                  skill_vs_random_walk=EXCLUDED.skill_vs_random_walk,
                                  skill_vs_seasonal_naive=EXCLUDED.skill_vs_seasonal_naive,
                                  n_undefined_scale=EXCLUDED.n_undefined_scale,
                                  min_train_used=EXCLUDED.min_train_used
                    """),
                    {
                        "p": protocol_id, "s": sid, "m": run.model, "h": run.horizon,
                        "n": s.n, "mase": s.mase, "mae": s.mae, "rmse": s.rmse,
                        "bias": s.bias, "e": run.engine,
                        "srw": skill_rw, "ssn": skill_sn,
                        "nu": s.n_undefined_scale,
                        "mt": min_train_for(run.model, "monthly", MIN_TRAIN),
                    },
                )

                # Persist every origin so comparisons can be made on common
                # target dates rather than on whatever each method happened to
                # score, and so the prototype can show the working.
                for o in run.origins:
                    target = periods[o.origin_index + run.horizon]
                    conn.execute(
                        text("""
                        INSERT INTO benchmark_origin
                          (protocol_id, series_id, model, horizon, origin_period,
                           target_period, forecast, actual, error, scale_q)
                        VALUES (:p,:s,:m,:h,:op,:tp,:f,:a,:e,:q)
                        ON CONFLICT (protocol_id, series_id, model, horizon, origin_period)
                        DO UPDATE SET forecast=EXCLUDED.forecast, actual=EXCLUDED.actual,
                                      error=EXCLUDED.error, scale_q=EXCLUDED.scale_q
                        """),
                        {"p": protocol_id, "s": sid, "m": run.model, "h": run.horizon,
                         "op": o.origin_period, "tp": target, "f": o.forecast,
                         "a": o.actual, "e": o.forecast - o.actual, "q": o.scale},
                    )
                mase_txt = f"{s.mase:.3f}" if s.mase is not None else "undef"
                skill_txt = f"{skill_rw:+.1%}" if skill_rw is not None else "  n/a"
                print(f"  {sid.split(':')[0]:8s} {run.model:16s} h={run.horizon} "
                      f"n={s.n:3d} MASE={mase_txt:>6s} MAE={s.mae:6.2f} "
                      f"skill_vs_RW={skill_txt} undef={s.n_undefined_scale}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
