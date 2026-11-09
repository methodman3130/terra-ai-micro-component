"""Feature construction for the gradient-boosted candidate.

Every feature is a function of observations dated at or before the origin.
There is no centred rolling window, no target encoding fitted on the full
series, and no calendar feature derived from the target period's own value.
Leakage in a price model is easy to introduce and nearly invisible in a score,
so the rule is enforced structurally: ``build_row`` is only ever handed the
training slice, never the full array.

Direct multi-horizon: a separate model is fitted per horizon, predicting h
steps ahead from the origin. Recursive forecasting would feed a model's own
output back as an input and compound its error without that showing up as
uncertainty.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Sequence

LAGS = (1, 2, 3, 6, 12)
ROLLING = (3, 6, 12)

FEATURE_NAMES: list[str] = (
    [f"lag_{l}" for l in LAGS]
    + [f"roll_mean_{w}" for w in ROLLING]
    + [f"roll_std_{w}" for w in ROLLING]
    + ["month_sin", "month_cos", "diff_1", "diff_12", "ratio_lag1_roll12"]
)


def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs)


def _std(xs: Sequence[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


@dataclass(frozen=True)
class Row:
    values: list[float]

    def as_list(self) -> list[float]:
        return self.values


def build_row(history: Sequence[float | None], target_period: date) -> list[float] | None:
    """Features for predicting ``target_period`` from ``history``.

    ``history`` ends at the origin. Returns None when the history is too short
    or too gappy to form a row — a refusal, not a zero-filled row.
    """
    clean = [v for v in history if v is not None]
    if len(clean) < max(LAGS) + 1:
        return None

    feats: list[float] = []
    for lag in LAGS:
        feats.append(float(clean[-lag]))
    for window in ROLLING:
        feats.append(_mean(clean[-window:]))
    for window in ROLLING:
        feats.append(_std(clean[-window:]))

    # Month of the *target* period is known in advance — it is a calendar fact,
    # not an observation, so using it is not leakage.
    month = target_period.month
    feats.append(math.sin(2 * math.pi * month / 12))
    feats.append(math.cos(2 * math.pi * month / 12))

    feats.append(float(clean[-1] - clean[-2]))
    feats.append(float(clean[-1] - clean[-12]))
    roll12 = _mean(clean[-12:])
    feats.append(float(clean[-1] / roll12) if roll12 else 1.0)

    return feats


def training_matrix(
    values: Sequence[float | None],
    periods: Sequence[date],
    origin: int,
    horizon: int,
    min_rows: int = 24,
) -> tuple[list[list[float]], list[float]] | None:
    """Assemble (X, y) using only data up to ``origin``.

    Each training row pairs features built from history ending at t with the
    observed value at t + horizon, for every t where both exist and t+horizon
    is still at or before the origin. Nothing after the origin is visible.
    """
    X: list[list[float]] = []
    y: list[float] = []
    for t in range(max(LAGS), origin - horizon + 1):
        target_index = t + horizon
        if target_index > origin:
            break
        target = values[target_index]
        if target is None:
            continue
        row = build_row(values[: t + 1], periods[target_index])
        if row is None:
            continue
        X.append(row)
        y.append(float(target))
    if len(X) < min_rows:
        return None
    return X, y
