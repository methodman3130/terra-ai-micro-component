"""Regression test for the horizon-matching bug.

The first implementation keyed baselines by model name alone, so a candidate at
h=1 was compared against a baseline at h=3 — a longer and harder task. On the
real carrot panel that reported AutoARIMA (MAE 9.15) as beating RandomWalk
whose h=1 MAE was 9.05. A false win is the worst possible defect in a benchmark
whose entire purpose is to say honestly whether anything beat the naive
forecast, so it is pinned here.
"""
from app.routers.benchmark import _beats_all_baselines


def row(model, horizon, mae):
    return {"model": model, "horizon": horizon, "mae": mae}


def test_candidate_is_compared_within_its_own_horizon():
    found = [
        row("RandomWalk", 1, 9.05),
        row("SeasonalNaive", 1, 13.14),
        row("AutoARIMA", 1, 9.15),      # worse than the h=1 random walk
        row("RandomWalk", 3, 17.17),
        row("SeasonalNaive", 3, 13.13),
        row("GradientBoosted", 3, 11.42),  # genuinely better than both at h=3
    ]
    assert _beats_all_baselines(found) == ["GradientBoosted@h3"]


def test_a_candidate_must_beat_every_baseline_not_just_one():
    found = [
        row("RandomWalk", 1, 5.0),
        row("SeasonalNaive", 1, 20.0),
        row("AutoETS", 1, 10.0),  # beats seasonal naive only
    ]
    assert _beats_all_baselines(found) == []


def test_no_baselines_at_a_horizon_yields_no_claimed_win():
    found = [row("GradientBoosted", 6, 1.0)]
    assert _beats_all_baselines(found) == []


def test_missing_mae_never_counts_as_a_win():
    found = [row("RandomWalk", 1, 9.0), row("AutoARIMA", 1, None)]
    assert _beats_all_baselines(found) == []
