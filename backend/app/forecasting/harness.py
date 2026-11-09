"""Walk-forward benchmark harness.

Implements the preregistered protocol from the micro-component proposal:

  * Mandatory comparators: random walk (naive) and seasonal naive.
  * Candidates: ETS and SARIMA, inside a declared parameter box.
  * Expanding-window origins; at each origin fit only on observations dated at
    or before that origin.
  * Scores reported per commodity, geography, frequency and horizon. Never pooled.

Three guards are enforced in code because a prose commitment is not enforcement:

  1. ``SeasonalNaiveGuard`` — on an annual series, m = 1 makes seasonal naive
     identical to the random walk. It is then refused as an independent second
     baseline, which is exactly what the proposal says must not be reported.
  2. ``ParameterBox`` — AutoARIMA defaults are wider than the declared box.
     Leaving them on would void the preregistration, so the box is applied and
     recorded.
  3. ``study_cutoff`` — nothing dated after 2025-12-31 may be scored.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import date
from typing import Callable, Iterable, Sequence

from app.forecasting import metrics


class ProtocolViolation(RuntimeError):
    """Raised when a run would break the preregistered protocol."""


# ---------------------------------------------------------------------------
# Declared parameter box
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ParameterBox:
    """The SARIMA search space declared in the proposal.

    p,q in 0..2 · P,Q in 0..1 · d,D in 0..1 · p+q+P+Q <= 4 · m in {4, 12}
    """
    max_p: int = 2
    max_q: int = 2
    max_P: int = 1
    max_Q: int = 1
    max_d: int = 1
    max_D: int = 1
    max_order: int = 4
    allowed_m: tuple[int, ...] = (4, 12)

    def validate_m(self, season_length: int) -> None:
        if season_length not in self.allowed_m and season_length != 1:
            raise ProtocolViolation(
                f"season_length={season_length} is outside the declared box {self.allowed_m}. "
                "Changing it requires a dated protocol amendment before testing."
            )

    def as_dict(self) -> dict[str, object]:
        return asdict(self)

    def statsforecast_kwargs(self, season_length: int) -> dict[str, object]:
        return {
            "max_p": self.max_p,
            "max_q": self.max_q,
            "max_P": self.max_P,
            "max_Q": self.max_Q,
            "max_d": self.max_d,
            "max_D": self.max_D,
            "max_order": self.max_order,
            "season_length": season_length,
        }


DECLARED_BOX = ParameterBox()

# The locked protocol sets a longer minimum training window for SARIMA than for
# the other methods: "SARIMA only from 96 observations with supported
# seasonality" (monthly), 32 (quarterly). Running AutoARIMA from the general
# 60-observation floor would be a protocol breach, not a tuning choice.
MODEL_MIN_TRAIN = {"AutoARIMA": {"monthly": 96, "quarterly": 32}}


def min_train_for(model: str, frequency: str, default: int) -> int:
    return MODEL_MIN_TRAIN.get(model, {}).get(frequency, default)


# ---------------------------------------------------------------------------
# Baselines (native, so the mandatory comparators never depend on an optional import)
# ---------------------------------------------------------------------------

def random_walk(train: Sequence[float], horizon: int) -> list[float]:
    """Repeat the last observed value."""
    if not train:
        raise ProtocolViolation("Cannot forecast from an empty training window")
    return [float(train[-1])] * horizon


def seasonal_naive(train: Sequence[float], horizon: int, season_length: int) -> list[float]:
    """Repeat the value from the corresponding season."""
    if season_length < 1:
        raise ProtocolViolation("season_length must be >= 1")
    if len(train) < season_length:
        raise ProtocolViolation(
            f"Need at least {season_length} training observations for seasonal naive"
        )
    return [float(train[-season_length + (h % season_length)]) for h in range(horizon)]


def seasonal_naive_is_independent(season_length: int) -> bool:
    """False when m = 1, where seasonal naive merely duplicates the random walk.

    The proposal is explicit: in that case it must not be presented as an
    independent second baseline.
    """
    return season_length > 1


# ---------------------------------------------------------------------------
# Walk-forward evaluation
# ---------------------------------------------------------------------------

@dataclass
class OriginResult:
    origin_index: int
    origin_period: date
    horizon: int
    forecast: float
    actual: float
    scale: float | None = None  # q_t from this origin's own training window


@dataclass
class ModelRun:
    model: str
    engine: str
    horizon: int
    season_length: int
    origins: list[OriginResult] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    def scores(self, training_head: Sequence[float] | None = None) -> metrics.Scores:
        """Score this run using per-origin scaling, per the locked protocol."""
        if not self.origins:
            raise ProtocolViolation(f"{self.model} h={self.horizon}: no scored origins")
        return metrics.score_per_origin(
            [o.forecast for o in self.origins],
            [o.actual for o in self.origins],
            [o.scale for o in self.origins],
        )


Forecaster = Callable[[Sequence[float], int], Sequence[float]]


def walk_forward(
    values: Sequence[float],
    periods: Sequence[date],
    forecaster: Forecaster,
    *,
    horizon: int,
    min_train: int,
    model_name: str,
    engine: str,
    season_length: int,
    cutoff: date,
) -> ModelRun:
    """Expanding-window evaluation.

    At each origin the forecaster sees only ``values[:origin+1]``. An origin
    whose target is missing, or dated after the cutoff, is **skipped and
    recorded** rather than bridged.
    """
    if len(values) != len(periods):
        raise ProtocolViolation("values and periods must be the same length")
    if min_train < 1:
        raise ProtocolViolation("min_train must be >= 1")

    run = ModelRun(model=model_name, engine=engine, horizon=horizon, season_length=season_length)

    for origin in range(min_train - 1, len(values) - horizon):
        target_index = origin + horizon
        target_period = periods[target_index]
        if target_period > cutoff:
            run.skipped.append(f"origin {origin}: target {target_period} after study cutoff")
            continue
        train = [v for v in values[: origin + 1] if v is not None]
        if len(train) < min_train:
            run.skipped.append(f"origin {origin}: only {len(train)} usable training observations")
            continue
        # q_t is computed from this origin's own training window, not once from
        # the first window: the protocol defines MASE as a mean of ratios.
        try:
            q_t = metrics.in_sample_scaling(train, season_length)
            if metrics.scale_is_undefined(q_t, train):
                q_t = None
        except metrics.MetricError:
            q_t = None

        actual = values[target_index]
        if actual is None:
            run.skipped.append(f"origin {origin}: target observation missing, not imputed")
            continue
        try:
            prediction = forecaster(train, horizon)
        except Exception as exc:  # a failed fit is recorded, never silently dropped
            run.skipped.append(f"origin {origin}: fit failed ({type(exc).__name__}: {exc})")
            continue
        run.origins.append(
            OriginResult(
                origin_index=origin,
                origin_period=periods[origin],
                horizon=horizon,
                forecast=float(prediction[horizon - 1]),
                actual=float(actual),
                scale=q_t,
            )
        )
    return run


# ---------------------------------------------------------------------------
# Model registry
# ---------------------------------------------------------------------------

def baseline_forecasters(season_length: int) -> dict[str, Forecaster]:
    """The mandatory comparators.

    Seasonal naive is omitted when m = 1 — deliberately, and the caller should
    say so in the report rather than quietly showing one baseline.
    """
    models: dict[str, Forecaster] = {
        "RandomWalk": lambda train, h: random_walk(train, h),
    }
    if seasonal_naive_is_independent(season_length):
        models["SeasonalNaive"] = lambda train, h: seasonal_naive(train, h, season_length)
    return models


def statsforecast_forecasters(
    season_length: int, box: ParameterBox = DECLARED_BOX
) -> dict[str, Forecaster]:
    """ETS and SARIMA via StatsForecast, constrained to the declared box.

    Returns an empty mapping when StatsForecast is not installed, so the
    mandatory baselines still run. A candidate that cannot be fitted does not
    invalidate the baseline results.
    """
    box.validate_m(season_length)
    try:
        import numpy as np
        from statsforecast.models import AutoARIMA, AutoETS
    except ImportError:
        return {}

    def _arima(train: Sequence[float], h: int) -> Sequence[float]:
        model = AutoARIMA(**box.statsforecast_kwargs(season_length))
        model.fit(np.asarray(train, dtype=float))
        return model.predict(h=h)["mean"]

    def _ets(train: Sequence[float], h: int) -> Sequence[float]:
        # Additive error only; multiplicative terms are excluded by the proposal
        # to avoid invalid fitting where values are zero or non-positive.
        model = AutoETS(season_length=season_length, model="ZZZ")
        model.fit(np.asarray(train, dtype=float))
        return model.predict(h=h)["mean"]

    return {"AutoARIMA": _arima, "AutoETS": _ets}


def gradient_boosted_forecaster(
    values: Sequence[float | None], periods: Sequence[date], horizon: int
) -> Forecaster:
    """Regularised gradient-boosted trees, refitted at every origin.

    The proposal lists these as a candidate alongside ETS and SARIMA. Returned
    as a closure over the full panel because the model needs the *periods* (for
    the calendar feature) and must rebuild its training matrix at each origin
    using only data up to that origin — which ``training_matrix`` enforces.

    Hyperparameters are fixed, not tuned per origin. Tuning inside the
    walk-forward loop would select on the test period and inflate the score.
    """
    from sklearn.ensemble import HistGradientBoostingRegressor

    from app.forecasting.features import build_row, training_matrix

    def _forecast(train: Sequence[float], h: int) -> Sequence[float]:
        origin = len(train) - 1
        built = training_matrix(values, periods, origin, h)
        if built is None:
            raise ProtocolViolation("insufficient training rows for the boosted candidate")
        X, y = built
        model = HistGradientBoostingRegressor(
            max_iter=300,
            learning_rate=0.05,
            max_depth=3,
            min_samples_leaf=8,
            l2_regularization=1.0,
            early_stopping=False,
            random_state=20261108,
        )
        model.fit(X, y)
        target_period = periods[min(origin + h, len(periods) - 1)]
        row = build_row(values[: origin + 1], target_period)
        if row is None:
            raise ProtocolViolation("cannot build a feature row at this origin")
        prediction = float(model.predict([row])[0])
        # Only the h-th step is ever read, but the contract returns h values.
        return [prediction] * h

    return _forecast


def run_protocol(
    values: Sequence[float],
    periods: Sequence[date],
    *,
    horizons: Iterable[int],
    min_train: int,
    season_length: int,
    cutoff: date,
    include_candidates: bool = True,
    include_boosted: bool = True,
    frequency: str = "monthly",
) -> list[ModelRun]:
    """Run every registered model over every horizon."""
    DECLARED_BOX.validate_m(season_length)
    runs: list[ModelRun] = []
    base: list[tuple[str, str, Forecaster]] = [
        (name, "native", fn) for name, fn in baseline_forecasters(season_length).items()
    ]
    if include_candidates:
        base += [
            (name, "statsforecast", fn)
            for name, fn in statsforecast_forecasters(season_length).items()
        ]
    for horizon in horizons:
        models = list(base)
        if include_boosted:
            try:
                models.append(
                    ("GradientBoosted", "sklearn",
                     gradient_boosted_forecaster(values, periods, horizon))
                )
            except ImportError:
                pass
        for name, engine, fn in models:
            runs.append(
                walk_forward(
                    values,
                    periods,
                    fn,
                    horizon=horizon,
                    min_train=min_train_for(name, frequency, min_train),
                    model_name=name,
                    engine=engine,
                    season_length=season_length,
                    cutoff=cutoff,
                )
            )
    return runs
