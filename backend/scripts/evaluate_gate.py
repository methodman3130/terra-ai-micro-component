"""Apply the proposal's locked go / revise / pause gate.

The gate is not a judgement call. The proposal fixes it in advance:

  Predictive evidence - "the development-selected candidate reduces paired
  final MAE by at least 10% versus both applicable naive methods, with
  MASE < 1 where defined". No gain: retain descriptive results and revise
  predictive scope.

  Evidence strength - "At least 24 monthly or 8 quarterly common final targets
  at the primary one-step horizon for each commodity claimed predictive-ready."

Two things this script does that an aggregate-score comparison cannot:

  * It compares on **common target dates**. SARIMA's minimum training window is
    96 monthly observations against 60 for the other methods, so it scores
    fewer origins; differencing the aggregate MAEs would compare different
    test sets and is not the "paired" comparison the gate specifies.
  * It applies the 10% threshold at the **primary one-step horizon**, which is
    what the evidence-strength row names. Gains at longer horizons are
    reported, but they do not by themselves pass this gate.

Usage:  python scripts/evaluate_gate.py [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, text

from app.config import settings

BASELINES = ("RandomWalk", "SeasonalNaive")
SKILL_THRESHOLD = 0.10
MIN_COMMON_TARGETS = 24
PRIMARY_HORIZON = 1


def paired_comparison(conn, protocol_id, series_id, horizon, candidate, baseline):
    """MAE of both methods over the target dates they BOTH scored."""
    rows = conn.execute(
        text("""
        SELECT c.target_period,
               abs(c.error) AS cand_abs,
               abs(b.error) AS base_abs,
               c.scale_q
        FROM benchmark_origin c
        JOIN benchmark_origin b
          ON b.protocol_id = c.protocol_id AND b.series_id = c.series_id
         AND b.horizon = c.horizon AND b.target_period = c.target_period
         AND b.model = :baseline
        WHERE c.protocol_id = :p AND c.series_id = :s
          AND c.horizon = :h AND c.model = :cand
        """),
        {"p": protocol_id, "s": series_id, "h": horizon,
         "cand": candidate, "baseline": baseline},
    ).mappings().all()

    if not rows:
        return None

    cand_mae = sum(r["cand_abs"] for r in rows) / len(rows)
    base_mae = sum(r["base_abs"] for r in rows) / len(rows)
    ratios = [r["cand_abs"] / r["scale_q"] for r in rows if r["scale_q"]]
    return {
        "baseline": baseline,
        "n_common": len(rows),
        "candidate_mae": cand_mae,
        "baseline_mae": base_mae,
        "skill": None if base_mae == 0 else 1.0 - cand_mae / base_mae,
        "candidate_mase": sum(ratios) / len(ratios) if ratios else None,
        "n_undefined_scale": len(rows) - len(ratios),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    engine = create_engine(settings.database_url)
    report: dict = {"threshold": SKILL_THRESHOLD, "primary_horizon": PRIMARY_HORIZON,
                    "min_common_targets": MIN_COMMON_TARGETS, "series": {}}

    with engine.connect() as conn:
        protocol_id = conn.execute(
            text("SELECT protocol_id FROM benchmark_protocol ORDER BY frozen_at DESC LIMIT 1")
        ).scalar_one()

        series_ids = [r[0] for r in conn.execute(
            text("SELECT DISTINCT series_id FROM benchmark_origin ORDER BY series_id")
        )]

        for sid in series_ids:
            candidates = [r[0] for r in conn.execute(
                # ANY(array) rather than IN (tuple): psycopg will not expand a
                # Python tuple into an IN list.
                text("""SELECT DISTINCT model FROM benchmark_origin
                        WHERE series_id = :s AND NOT (model = ANY(:b))
                        ORDER BY model"""),
                {"s": sid, "b": list(BASELINES)},
            )]
            horizons = [r[0] for r in conn.execute(
                text("SELECT DISTINCT horizon FROM benchmark_origin WHERE series_id = :s "
                     "ORDER BY horizon"), {"s": sid},
            )]

            entry: dict = {"horizons": {}}
            for h in horizons:
                per_candidate = {}
                for cand in candidates:
                    comparisons = [
                        c for c in (
                            paired_comparison(conn, protocol_id, sid, h, cand, b)
                            for b in BASELINES
                        ) if c is not None
                    ]
                    if not comparisons:
                        continue
                    beats_all = all(
                        c["skill"] is not None and c["skill"] >= SKILL_THRESHOLD
                        for c in comparisons
                    )
                    mase_ok = all(
                        c["candidate_mase"] is None or c["candidate_mase"] < 1.0
                        for c in comparisons
                    )
                    enough = min(c["n_common"] for c in comparisons) >= MIN_COMMON_TARGETS
                    per_candidate[cand] = {
                        "comparisons": comparisons,
                        "meets_skill_threshold": beats_all,
                        "mase_below_one": mase_ok,
                        "sufficient_common_targets": enough,
                        "passes": beats_all and mase_ok and enough,
                    }
                entry["horizons"][h] = per_candidate

            primary = entry["horizons"].get(PRIMARY_HORIZON, {})
            passing = [c for c, v in primary.items() if v["passes"]]
            entry["verdict"] = "go" if passing else "revise"
            entry["passing_candidates_at_primary_horizon"] = passing
            # Reported, but explicitly not a pass: the gate names the one-step
            # horizon, so a longer-horizon gain cannot carry the decision.
            entry["longer_horizon_gains"] = {
                h: [c for c, v in cands.items() if v["passes"]]
                for h, cands in entry["horizons"].items() if h != PRIMARY_HORIZON
            }
            report["series"][sid] = entry

    report["overall_verdict"] = (
        "go" if all(e["verdict"] == "go" for e in report["series"].values())
        else "revise"
    )

    if args.json:
        print(json.dumps(report, indent=2, default=float))
        return 0

    print(f"\nGATE EVALUATION - threshold {SKILL_THRESHOLD:.0%} paired MAE reduction "
          f"vs BOTH baselines, MASE < 1, >= {MIN_COMMON_TARGETS} common targets, "
          f"at h={PRIMARY_HORIZON}\n")
    for sid, entry in report["series"].items():
        print(f"{sid}")
        for h, cands in entry["horizons"].items():
            for cand, v in cands.items():
                bits = " ".join(
                    f"vs {c['baseline']}: skill={c['skill']:+.1%} "
                    f"(n={c['n_common']}, MASE={c['candidate_mase']:.2f})"
                    if c["skill"] is not None and c["candidate_mase"] is not None else
                    f"vs {c['baseline']}: undefined"
                    for c in v["comparisons"]
                )
                mark = "PASS" if v["passes"] else "    "
                print(f"  h={h} {cand:16s} {mark}  {bits}")
        print(f"  -> verdict at h={PRIMARY_HORIZON}: {entry['verdict'].upper()}"
              f"{' (' + ', '.join(entry['passing_candidates_at_primary_horizon']) + ')' if entry['passing_candidates_at_primary_horizon'] else ''}")
        longer = {h: c for h, c in entry["longer_horizon_gains"].items() if c}
        if longer:
            print(f"  -> gains at longer horizons (reported, not a gate pass): {longer}")
        print()

    print(f"OVERALL: {report['overall_verdict'].upper()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
