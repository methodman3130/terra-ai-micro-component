"""CC BY attribution.

OpenSTAT is licensed CC BY (verified 5 Nov 2026). The licence is satisfied only
if the credit travels with the data, so attribution is produced here and
attached to every response envelope — not written into a page footer that an
export would drop.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.config import ATTRIBUTION_TEMPLATE

LICENCE_URL = "https://creativecommons.org/licenses/by/4.0/"
SOURCE_URL = "https://openstat.psa.gov.ph/"


@dataclass(frozen=True)
class Attribution:
    text: str
    licence: str = "CC BY 4.0"
    licence_url: str = LICENCE_URL
    source_url: str = SOURCE_URL
    endorsement_disclaimer: str = (
        "The Philippine Statistics Authority does not endorse this use."
    )

    def as_dict(self) -> dict[str, str]:
        return {
            "text": self.text,
            "licence": self.licence,
            "licence_url": self.licence_url,
            "source_url": self.source_url,
            "disclaimer": self.endorsement_disclaimer,
        }


def render(table: str, title: str, retrieved: str, modifications: str) -> Attribution:
    """Build the credit line.

    ``modifications`` must be a real description. The licence requires stating
    whether changes were made, so an empty string is refused rather than
    silently producing a non-compliant credit.
    """
    if not modifications.strip():
        raise ValueError(
            "CC BY requires stating what was changed. Describe the modifications "
            "(e.g. 'reshaped to long form, units normalised, no values altered')."
        )
    return Attribution(
        text=ATTRIBUTION_TEMPLATE.format(
            table=table, title=title, retrieved=retrieved, modifications=modifications.strip()
        )
    )


STANDARD_MODIFICATIONS = (
    "reshaped from PXWeb wide format to long form, periods normalised to ISO dates, "
    "quality flags added; published values were not altered"
)
