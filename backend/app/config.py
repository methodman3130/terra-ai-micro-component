"""Configuration. No credential is ever written in source."""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env(key: str, default: str | None = None) -> str:
    value = os.environ.get(key, default)
    if value is None:
        raise RuntimeError(
            f"Required environment variable {key} is not set. "
            "Copy .env.example to .env and fill it in; never hardcode credentials."
        )
    return value


@dataclass(frozen=True)
class Settings:
    database_url: str = field(default_factory=lambda: _env(
        "TERRA_DATABASE_URL", "postgresql+psycopg://terra:terra@localhost:5432/terra"
    ))
    openstat_base: str = field(default_factory=lambda: _env(
        "TERRA_OPENSTAT_BASE", "https://openstat.psa.gov.ph/PXWeb/api/v1/en"
    ))
    raw_dir: str = field(default_factory=lambda: _env("TERRA_RAW_DIR", "./data/raw"))
    # Observations after this date are not scoreable: the study window closes 2025-12-31.
    study_cutoff: str = field(default_factory=lambda: _env("TERRA_STUDY_CUTOFF", "2025-12-31"))
    request_timeout: int = 60
    user_agent: str = "TERRA-AI-MicroComponent/0.1 (University of the Cordilleras research prototype)"


settings = Settings()

# The CC BY obligation, rendered once and carried on every extract and export.
ATTRIBUTION_TEMPLATE = (
    "Source: Philippine Statistics Authority, OpenSTAT, table {table} ({title}). "
    "Retrieved {retrieved}. Licensed CC BY 4.0. "
    "Modified by the University of the Cordilleras for the Project TERRA-AI Micro-Component: "
    "{modifications}. PSA does not endorse this use."
)
