"""Series register: deterministic identity, and the freeze that makes
preregistration meaningful.

A series may be scored only after it is frozen. Freezing records a hash over the
ordered observation keys, so if the underlying panel is later re-retrieved and
the shape changes, the mismatch is detectable rather than silent.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date
from typing import Iterable, Sequence

_SLUG = re.compile(r"[^a-z0-9]+")

VALID_FREQUENCIES = ("annual", "quarterly", "monthly", "daily")
VALID_VARIABLES = ("farmgate_price", "production", "area_harvested")


def slug(value: str) -> str:
    return _SLUG.sub("-", value.strip().casefold()).strip("-")


@dataclass(frozen=True)
class SeriesKey:
    commodity: str
    variable: str
    geography_code: str
    frequency: str
    unit: str
    grade_variety: str | None = None

    def __post_init__(self) -> None:
        if self.variable not in VALID_VARIABLES:
            raise ValueError(f"variable must be one of {VALID_VARIABLES}, got {self.variable!r}")
        if self.frequency not in VALID_FREQUENCIES:
            raise ValueError(f"frequency must be one of {VALID_FREQUENCIES}, got {self.frequency!r}")

    @property
    def series_id(self) -> str:
        """Stable identifier. Grade and variety are part of series identity:
        a different grade is a different series, not a revision of the same one.
        """
        parts = [
            slug(self.commodity),
            slug(self.variable),
            self.geography_code.strip(),
            self.frequency,
            slug(self.unit),
        ]
        if self.grade_variety:
            parts.append(slug(self.grade_variety))
        return ":".join(parts)


def freeze_hash(periods: Iterable[date]) -> str:
    """Hash of the ordered period keys. Values are deliberately excluded —
    PSA revises values, and a revision should not look like a shape change.
    """
    ordered = sorted(periods)
    if not ordered:
        raise ValueError("Cannot freeze an empty series")
    joined = "|".join(p.isoformat() for p in ordered)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def verify_freeze(frozen: str, periods: Sequence[date]) -> bool:
    return freeze_hash(periods) == frozen


def min_observations(frequency: str) -> int:
    """Conservative project rules from the proposal. These are floors for
    *attempting* a fit, not guarantees of statistical validity.
    """
    return {"monthly": 60, "quarterly": 20, "annual": 10, "daily": 180}[frequency]
