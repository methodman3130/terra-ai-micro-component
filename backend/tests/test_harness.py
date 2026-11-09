"""The protocol guards are the point of these tests.

Each one corresponds to a commitment in the micro-component proposal that would
otherwise live only in prose.
"""
from datetime import date

import pytest

from app.forecasting import harness
from app.forecasting.features import training_matrix


def monthly_periods(n, start_year=2015):
    out = []
    y, m = start_year, 1
    for _ in range(n):
        out.append(date(y, m, 1))
        m += 1
        if m == 13:
            m, y = 1, y + 1
    return out


def test_random_walk_repeats_last_value():
    assert harness.random_walk([1.0, 2.0, 7.0], 3) == [7.0, 7.0, 7.0]


def test_seasonal_naive_repeats_corresponding_season():
    train = [1.0, 2.0, 3.0, 4.0]  # m=4
    assert harness.seasonal_naive(train, 4, 4) == [1.0, 2.0, 3.0, 4.0]


def test_seasonal_naive_is_not_independent_at_m_equals_one():
    assert harness.seasonal_naive_is_independent(1) is False
    assert harness.seasonal_naive_is_independent(12) is True


def test_annual_protocol_omits_seasonal_naive_as_second_baseline():
    models = harness.baseline_forecasters(season_length=1)
    assert list(models) == ["RandomWalk"]


def test_monthly_protocol_includes_both_baselines():
    models = harness.baseline_forecasters(season_length=12)
    assert set(models) == {"RandomWalk", "SeasonalNaive"}


def test_declared_box_refuses_undeclared_season_length():
    with pytest.raises(harness.ProtocolViolation):
        harness.DECLARED_BOX.validate_m(7)
    harness.DECLARED_BOX.validate_m(12)  # allowed
    harness.DECLARED_BOX.validate_m(1)   # annual, allowed


def test_declared_box_is_narrower_than_library_defaults():
    box = harness.DECLARED_BOX.statsforecast_kwargs(12)
    assert box["max_p"] == 2 and box["max_q"] == 2
    assert box["max_P"] == 1 and box["max_Q"] == 1
    assert box["max_order"] == 4


def test_walk_forward_never_sees_the_future():
    seen = []

    def spy(train, h):
        seen.append(len(train))
        return [train[-1]] * h

    values = [float(i) for i in range(24)]
    periods = monthly_periods(24)
    run = harness.walk_forward(
        values, periods, spy, horizon=1, min_train=12,
        model_name="spy", engine="native", season_length=12, cutoff=date(2030, 1, 1),
    )
    # First origin index is min_train-1 = 11, so the first training window is 12 long
    assert seen[0] == 12
    assert all(a < b for a, b in zip(seen, seen[1:]))  # expanding
    assert run.origins[0].forecast == 11.0
    assert run.origins[0].actual == 12.0


def test_targets_after_cutoff_are_skipped_and_recorded():
    values = [float(i) for i in range(24)]
    periods = monthly_periods(24)  # 2015-01 .. 2016-12
    run = harness.walk_forward(
        values, periods, lambda t, h: [t[-1]] * h, horizon=1, min_train=12,
        model_name="rw", engine="native", season_length=12, cutoff=date(2016, 6, 1),
    )
    assert run.skipped, "post-cutoff origins must be recorded, not silently dropped"
    assert all(o.origin_period <= date(2016, 6, 1) for o in run.origins)
    assert any("after study cutoff" in s for s in run.skipped)


def test_missing_target_is_skipped_not_imputed():
    values = [1.0, 2.0, 3.0, None, 5.0, 6.0, 7.0, 8.0]
    periods = monthly_periods(8)
    run = harness.walk_forward(
        values, periods, lambda t, h: [t[-1]] * h, horizon=1, min_train=2,
        model_name="rw", engine="native", season_length=1, cutoff=date(2030, 1, 1),
    )
    assert any("not imputed" in s for s in run.skipped)
    assert all(o.actual is not None for o in run.origins)


def test_failed_fit_is_recorded_not_swallowed():
    def explodes(train, h):
        raise ValueError("singular matrix")

    values = [float(i) for i in range(10)]
    run = harness.walk_forward(
        values, monthly_periods(10), explodes, horizon=1, min_train=3,
        model_name="bad", engine="native", season_length=1, cutoff=date(2030, 1, 1),
    )
    assert run.origins == []
    assert all("fit failed" in s for s in run.skipped)


def test_perfectly_periodic_series_gives_undefined_mase_not_infinity():
    """A seasonal difference of exactly zero makes MASE undefined.

    Synthetic data hits this; real farmgate prices will not. The behaviour is
    pinned here so nobody later 'fixes' it by substituting a tiny epsilon,
    which would silently manufacture a finite score out of a degenerate one.
    """
    values = [10.0 + (i % 12) for i in range(60)]
    periods = monthly_periods(60)
    runs = harness.run_protocol(
        values, periods, horizons=[1], min_train=24,
        season_length=12, cutoff=date(2030, 1, 1), include_candidates=False,
        include_boosted=False,
    )
    scores = runs[0].scores()
    assert scores.mase is None
    assert scores.scaling is None
    # Every origin's q_t is zero here, so all are counted as undefined rather
    # than silently dropped. The protocol requires that count to be published.
    assert scores.n_undefined_scale == len(runs[0].origins)
    assert scores.mae > 0  # the unscaled measures are still reported


def test_run_protocol_scores_baselines_without_optional_libraries():
    # Strong seasonal shape plus a slight trend: the trend makes the seasonal
    # difference non-zero (so MASE is defined) without swamping the seasonality.
    values = [10.0 + 5.0 * (i % 12) + 0.05 * i for i in range(60)]
    periods = monthly_periods(60)
    runs = harness.run_protocol(
        values, periods, horizons=[1, 2], min_train=24,
        season_length=12, cutoff=date(2030, 1, 1), include_candidates=False,
        include_boosted=False,
    )
    assert {r.model for r in runs} == {"RandomWalk", "SeasonalNaive"}
    assert {r.horizon for r in runs} == {1, 2}
    for r in runs:
        scores = r.scores()
        assert scores.n > 0
        assert scores.mase is not None
        assert scores.n_undefined_scale == 0
    # Seasonal naive should win on a purely seasonal series
    sn = next(r for r in runs if r.model == "SeasonalNaive" and r.horizon == 1)
    rw = next(r for r in runs if r.model == "RandomWalk" and r.horizon == 1)
    assert sn.scores().mae < rw.scores().mae


def test_boosted_features_never_use_the_future():
    """The boosted candidate must not see a value at or after its target."""
    from app.forecasting.features import training_matrix

    periods = monthly_periods(80)
    values = [float(i) for i in range(80)]
    # Poison everything after the origin; a leaking implementation would use it.
    origin = 50
    poisoned = list(values)
    for i in range(origin + 1, len(poisoned)):
        poisoned[i] = 1e9

    a = training_matrix(values, periods, origin, horizon=3)
    b = training_matrix(poisoned, periods, origin, horizon=3)
    assert a is not None and b is not None
    assert a == b, "training matrix changed when only post-origin values changed"


def test_training_matrix_refuses_rather_than_pads_a_short_history():
    periods = monthly_periods(20)
    values = [float(i) for i in range(20)]
    assert training_matrix(values, periods, origin=14, horizon=1) is None


def test_mase_uses_per_origin_scaling_not_one_fixed_window():
    """The protocol defines MASE as a mean of ratios, scaled at each origin.

    A fixed scaling from the first training window gives a ratio of means - a
    different statistic that misstates errors on a series whose level drifts.
    This fixture drifts hard, so the two disagree.
    """
    from app.forecasting import metrics

    periods = monthly_periods(90)
    # Volatility regime-shifts partway through, which is what makes the two
    # statistics diverge: a constant-amplitude series gives the same q_t at
    # every origin and the distinction would be invisible.
    values = [
        10.0 + (2.0 if i < 45 else 20.0) * (i % 12) + 0.3 * i
        for i in range(90)
    ]
    run = harness.walk_forward(
        values, periods, lambda t, h: [t[-1]] * h, horizon=1, min_train=60,
        model_name="rw", engine="native", season_length=12, cutoff=date(2030, 1, 1),
    )
    per_origin = run.scores().mase
    fixed = metrics.score(
        [o.forecast for o in run.origins], [o.actual for o in run.origins],
        training=[v for v in values[:60]], season_length=12,
    ).mase
    assert per_origin is not None and fixed is not None
    assert per_origin != pytest.approx(fixed, rel=1e-6)


def test_sarima_minimum_training_window_is_longer_than_the_general_floor():
    """Protocol: "SARIMA only from 96 observations" at monthly frequency."""
    assert harness.min_train_for("AutoARIMA", "monthly", 60) == 96
    assert harness.min_train_for("AutoARIMA", "quarterly", 20) == 32
    assert harness.min_train_for("AutoETS", "monthly", 60) == 60
    assert harness.min_train_for("RandomWalk", "monthly", 60) == 60
