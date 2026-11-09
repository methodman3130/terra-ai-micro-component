"""PSA OpenSTAT (PXWeb) client.

Two traps are handled here deliberately, both discovered against the live portal
on 10 Sep 2026 and re-confirmed in the 5 Nov 2026 market research:

  1. Request ``response.format = "csv"``. This PXWeb deployment's ``json-stat2``
     returns a ``size`` header that does not match the length of its ``value``
     array, so the JSON path silently mis-aligns dimensions.

  2. Resolve variable codes **by label**, every time. Crop code indices differ
     between the production table and the area table, so a code memorised from
     one table selects the wrong crop in the other.

Network note: the cloud container cannot reach openstat.psa.gov.ph (egress proxy
returns 403 on CONNECT). Run retrieval from the Windows host. The client is
written so that an offline caller can still exercise the parser via
``parse_csv`` on a saved file.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

try:  # requests is optional so the parser can be tested without it
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore

from app.config import settings


class OpenStatError(RuntimeError):
    pass


class VariableNotFound(OpenStatError):
    """A requested label does not exist in the table's metadata."""


@dataclass(frozen=True)
class Extract:
    """An immutable record of one retrieval. Mirrors ``source_extract``."""
    source_table: str
    source_table_title: str
    source_url: str
    selected_dimensions: dict[str, list[str]]
    retrieved_at: str
    reference_period: str
    vintage: str
    raw_checksum: str
    raw_path: str
    release_date: str | None = None
    permitted_use: str = "CC BY 4.0"

    def as_row(self) -> dict[str, Any]:
        row = asdict(self)
        row["selected_dimensions"] = json.dumps(self.selected_dimensions)
        return row


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def resolve_codes_by_label(
    metadata: dict[str, Any], variable_code: str, wanted_labels: Sequence[str]
) -> list[str]:
    """Map human labels to this table's value codes.

    Never cache the result across tables. That is trap #2.
    """
    for variable in metadata.get("variables", []):
        if variable.get("code") != variable_code:
            continue
        pairs = dict(zip(variable.get("valueTexts", []), variable.get("values", [])))
        # Case- and space-insensitive match; PSA labels are inconsistently cased.
        folded = {k.strip().casefold(): v for k, v in pairs.items()}
        resolved: list[str] = []
        missing: list[str] = []
        for label in wanted_labels:
            code = folded.get(label.strip().casefold())
            if code is None:
                missing.append(label)
            else:
                resolved.append(code)
        if missing:
            available = ", ".join(sorted(pairs)[:12])
            raise VariableNotFound(
                f"Labels {missing!r} not present in variable {variable_code!r}. "
                f"Available (first 12): {available}"
            )
        return resolved
    raise VariableNotFound(f"Variable {variable_code!r} not present in table metadata")


def build_query(selection: dict[str, Sequence[str]]) -> dict[str, Any]:
    """PXWeb query body. ``response.format`` is csv — that is trap #1."""
    return {
        "query": [
            {
                "code": code,
                "selection": {"filter": "item", "values": list(values)},
            }
            for code, values in selection.items()
        ],
        "response": {"format": "csv"},
    }


def parse_csv(payload: bytes) -> tuple[list[str], list[list[str]]]:
    """Parse a PXWeb CSV response into a header and rows.

    PXWeb emits a quoted header whose trailing columns are the time periods.
    No type coercion happens here: values stay as published strings so the
    cleaning layer can record exactly what arrived.
    """
    text = payload.decode("utf-8-sig", errors="strict")
    reader = csv.reader(io.StringIO(text))
    rows = [r for r in reader if any(cell.strip() for cell in r)]
    if not rows:
        raise OpenStatError("Empty CSV response from OpenSTAT")
    header, *body = rows
    header = [h.strip().strip('"') for h in header]
    return header, body


def to_long(
    header: Sequence[str], rows: Iterable[Sequence[str]], n_key_columns: int
) -> list[dict[str, str]]:
    """Melt PXWeb's wide period columns into long records.

    The first ``n_key_columns`` header entries identify the series (geography,
    commodity, ...); everything after them is a period.
    """
    periods = list(header[n_key_columns:])
    keys = list(header[:n_key_columns])
    out: list[dict[str, str]] = []
    for row in rows:
        if len(row) < n_key_columns:
            continue
        key_values = {k: row[i].strip().strip('"') for i, k in enumerate(keys)}
        for offset, period in enumerate(periods):
            index = n_key_columns + offset
            raw = row[index].strip().strip('"') if index < len(row) else ""
            out.append({**key_values, "period": period.strip().strip('"'), "value": raw})
    return out


def fetch_table(
    table_id: str,
    db_path: str,
    selection_labels: dict[str, Sequence[str]],
    *,
    reference_period: str,
    raw_dir: str | None = None,
    session: Any | None = None,
) -> tuple[Extract, bytes]:
    """Retrieve one table and write the immutable raw file.

    ``selection_labels`` is keyed by PXWeb variable code and valued by the
    *labels* we want. Codes are resolved against this table's own metadata.
    """
    if requests is None and session is None:  # pragma: no cover
        raise OpenStatError("requests is not installed and no session was supplied")
    http = session or requests.Session()
    http.headers.update({"User-Agent": settings.user_agent})

    url = f"{settings.openstat_base}/{db_path}/{table_id}"

    meta_response = http.get(url, timeout=settings.request_timeout)
    meta_response.raise_for_status()
    metadata = meta_response.json()

    selection = {
        code: resolve_codes_by_label(metadata, code, labels)
        for code, labels in selection_labels.items()
    }

    data_response = http.post(
        url, json=build_query(selection), timeout=settings.request_timeout
    )
    data_response.raise_for_status()
    payload = data_response.content

    retrieved_at = datetime.now(timezone.utc)
    checksum = sha256_bytes(payload)
    target_dir = Path(raw_dir or settings.raw_dir) / table_id
    target_dir.mkdir(parents=True, exist_ok=True)
    raw_path = target_dir / f"{retrieved_at:%Y%m%dT%H%M%SZ}_{checksum[:12]}.csv"
    raw_path.write_bytes(payload)
    os.chmod(raw_path, 0o444)  # immutable raw layer: read-only once written

    extract = Extract(
        source_table=table_id,
        source_table_title=metadata.get("title", table_id),
        source_url=url,
        selected_dimensions={k: list(v) for k, v in selection.items()},
        retrieved_at=retrieved_at.isoformat(),
        reference_period=reference_period,
        vintage=retrieved_at.strftime("%Y-%m"),
        raw_checksum=checksum,
        raw_path=str(raw_path),
    )
    return extract, payload


# Verified table identifiers (10 Sep 2026). Re-verify before each campaign:
# a table that moves is a protocol amendment, not a silent fix.
VERIFIED_TABLES = {
    "vegetable_production": "0082E4EVCP3",
    "vegetable_area": "0112E4EAHM3",
    "palay_corn_production": "0012E4EVCP0",
    "palay_corn_area": "0022E4EAHC0",
    "farmgate_price_leafy": "0032M4AFN06",
    "farmgate_price_rootcrop": "0032M4AFN02",
}
