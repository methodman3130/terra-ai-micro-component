"""Forecast error measures, implemented natively.

Implemented here rather than imported so that the audit does not rest on one
library's internals, and so the scaling quantity behind MASE is explicit and
stored. Hyndman & Koehler (2006) is the reference.

Sign convention fixed by the proposal: e = forecast - actual, so a positive
mean error means overforecasting.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence


class MetricError(ValueError):
    pass


# Proposal, measures table: "If q_t is zero or no greater than 1e-12 x
# max(1, mean |training y|), mark that scaled error undefined."
UNDEFINED_SCALE_FACTOR = 1e-12


def scale_is_undefined(q_t: float, training: Sequence[float]) -> bool:
    values = [abs(float(v)) for v in training if v is not None]
    reference = max(1.0, sum(values) / len(values)) if values else 1.0
    return q_t <= UNDEFINED_SCALE_FACTOR * reference


@dataclass(frozen=True)
class Scores:
    n: int
    mae: float
    rmse: float
    bias: float
    mase: float | None
    scaling: float | None
    scaling_basis: str
    n_undefined_scale: int = 0

    def as_row(self) -> dict[str, float | int | str | None]:
        return {
            "n_origins": self.n,
            "mae": self.mae,
            "rmse": self.rmse,
            "bias": self.bias,
            "mase": self.mase,
            "scaling": self.scaling,
            "scaling_basis": self.scaling_basis,
            "n_undefined_scale": self.n_undefined_scale,
        }


def _clean_pairs(
    forecast: Sequence[float], actual: Sequence[float]
) -> tuple[list[float], list[float]]:
    if len(forecast) != len(actual):
        raise MetricError(
            f"forecast and actual lengths differ: {len(forecast)} vs {len(actual)}"
        )
    f_out: list[float] = []
    a_out: list[float] = []
    for f, a in zip(forecast, actual):
        if f is None or a is None:
            continue
        if isinstance(f, float) and math.isnan(f):
            continue
        if isinstance(a, float) and math.isnan(a):
            continue
        f_out.append(float(f))
        a_out.append(float(a))
    if not f_out:
        raise MetricError("No matched forecast/actual pairs to score")
    return f_out, a_out


def mae(forecast: Sequence[float], actual: Sequence[float]) -> float:
    f, a = _clean_pairs(forecast, actual)
    return sum(abs(x - y) for x, y in zip(f, a)) / len(f)


def rmse(forecast: Sequence[float], actual: Sequence[float]) -> float:
    f, a = _clean_pairs(forecast, actual)
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(f, a)) / len(f))


def bias(forecast: Sequence[float], actual: Sequence[float]) -> float:
    """Mean error. Positive = overforecasting."""
    f, a = _clean_pairs(forecast, actual)
    return sum(x - y for x, y in zip(f, a)) / len(f)


def in_sample_scaling(training: Sequence[float], season_length: int = 1) -> float:
    """Mean absolute (seasonal) difference of the training series.

    This is the denominator of MASE and must be stored alongside the score:
    a MASE is uninterpretable without knowing what it was scaled against.
    """
    if season_length < 1:
        raise MetricError("season_length must be >= 1")
    values = [float(v) for v in training if v is not None and not (isinstance(v, float) and math.isnan(v))]
    if len(values) <= season_length:
        raise MetricError(
            f"Need more than {season_length} training observations to compute scaling, got {len(values)}"
        )
    diffs = [abs(values[i] - values[i - season_length]) for i in range(season_length, len(values))]
    scale = sum(diffs) / len(diffs)
    if scale == 0:
        raise MetricError(
            "In-sample scaling is zero (constant training series); MASE is undefined"
        )
    return scale


def score(
    forecast: Sequence[float],
    actual: Sequence[float],
    training: Sequence[float] | None = None,
    season_length: int = 1,
) -> Scores:
    """Full score set. MASE is omitted — not faked — when scaling is undefined."""
    f, a = _clean_pairs(forecast, actual)
    scaling: float | None = None
    mase_value: float | None = None
    basis = "unavailable"
    if training is not None:
        try:
            scaling = in_sample_scaling(training, season_length)
            mase_value = mae(f, a) / scaling
            basis = f"in-sample mean absolute difference, season_length={season_length}"
        except MetricError:
            scaling = None
            mase_value = None
            basis = "undefined (constant or too-short training series)"
    return Scores(
        n=len(f),
        mae=mae(f, a),
        rmse=rmse(f, a),
        bias=bias(f, a),
        mase=mase_value,
        scaling=scaling,
        scaling_basis=basis,
    )


def score_per_origin(
    forecast: Sequence[float],
    actual: Sequence[float],
    scales: Sequence[float | None],
) -> Scores:
    """MASE scaled at each origin, as the locked protocol requires.

    The proposal defines q_t over *that origin's* training data and the final
    MASE as mean(|e_t,h| / q_t) - a mean of ratios. Using one fixed scaling
    computed from the first training window instead gives a ratio of means,
    which is a different statistic: on a series whose level rises over sixteen
    years it understates early errors and overstates late ones.

    Origins whose q_t is undefined keep their MAE and RMSE contribution and are
    excluded from MASE only, with the count published rather than hidden.
    """
    f, a = _clean_pairs(forecast, actual)
    if len(scales) != len(forecast):
        raise MetricError("scales must align with forecasts")

    ratios: list[float] = []
    undefined = 0
    used_scales: list[float] = []
    for fc, ac, q in zip(forecast, actual, scales):
        if fc is None or ac is None:
            continue
        if q is None:
            undefined += 1
            continue
        ratios.append(abs(float(fc) - float(ac)) / q)
        used_scales.append(q)

    mase_value = sum(ratios) / len(ratios) if ratios else None
    mean_scale = sum(used_scales) / len(used_scales) if used_scales else None
    return Scores(
        n=len(f),
        mae=mae(f, a),
        rmse=rmse(f, a),
        bias=bias(f, a),
        mase=mase_value,
        scaling=mean_scale,
        scaling_basis=(
            "per-origin q_t = mean |y_i - y_(i-m)| over that origin's training data; "
            "MASE = mean(|e|/q_t). Reported scaling is the mean q_t across origins."
        ),
        n_undefined_scale=undefined,
    )


def relative_skill(candidate_mae: float, baseline_mae: float) -> float | None:
    """1 - candidate MAE / baseline MAE. Undefined when the baseline is zero."""
    if baseline_mae == 0:
        return None
    return 1.0 - (candidate_mae / baseline_mae)
