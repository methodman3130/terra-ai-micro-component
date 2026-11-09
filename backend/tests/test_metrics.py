import math

import pytest

from app.forecasting import metrics


def test_mae_rmse_bias_basic():
    forecast = [10.0, 12.0, 14.0]
    actual = [9.0, 13.0, 14.0]
    assert metrics.mae(forecast, actual) == pytest.approx(2 / 3)
    assert metrics.rmse(forecast, actual) == pytest.approx(math.sqrt(2 / 3))
    # +1, -1, 0 -> mean 0
    assert metrics.bias(forecast, actual) == pytest.approx(0.0)


def test_bias_sign_is_overforecast_positive():
    assert metrics.bias([10.0], [5.0]) > 0
    assert metrics.bias([5.0], [10.0]) < 0


def test_scaling_is_mean_absolute_difference():
    # diffs: 1, 1, 1 -> 1.0
    assert metrics.in_sample_scaling([1, 2, 3, 4], 1) == pytest.approx(1.0)
    # seasonal, m=2: |3-1|, |4-2| -> 2.0
    assert metrics.in_sample_scaling([1, 2, 3, 4], 2) == pytest.approx(2.0)


def test_constant_training_series_gives_no_mase_rather_than_infinity():
    scores = metrics.score([5.0, 5.0], [4.0, 6.0], training=[3.0, 3.0, 3.0])
    assert scores.mase is None
    assert "undefined" in scores.scaling_basis
    assert scores.mae == pytest.approx(1.0)


def test_mase_is_mae_over_scaling_and_scaling_is_reported():
    training = [1, 2, 3, 4]  # scaling 1.0
    scores = metrics.score([10.0], [8.0], training=training)
    assert scores.scaling == pytest.approx(1.0)
    assert scores.mase == pytest.approx(2.0)
    assert "season_length=1" in scores.scaling_basis


def test_length_mismatch_is_refused():
    with pytest.raises(metrics.MetricError):
        metrics.mae([1.0, 2.0], [1.0])


def test_nan_pairs_are_dropped_not_zero_filled():
    scores = metrics.score([1.0, float("nan"), 3.0], [2.0, 5.0, 4.0])
    assert scores.n == 2
    assert scores.mae == pytest.approx(1.0)


def test_all_missing_pairs_raises_rather_than_returning_zero():
    with pytest.raises(metrics.MetricError):
        metrics.score([float("nan")], [float("nan")])
