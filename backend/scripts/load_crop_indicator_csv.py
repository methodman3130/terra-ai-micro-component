"""Load a downloaded PSA quarterly crop indicator CSV into TERRA-AI.

Use this for the PSA OpenSTAT *Production* and *Area Harvested* extracts.
It intentionally accepts a saved CSV rather than retrieving from a web route:
the deploy environment cannot POST to OpenSTAT, while the research host can
retain the exact response and checksum as part of the provenance record.

Example (run twice, once for each variable)::

    python scripts/load_crop_indicator_csv.py --variable production \
      --table 0082E4EVCP3 --title "Vegetables: Volume of Production" \
      --unit "metric tons" --csv data/raw/production.csv
"""
from __future__ import annotations

import argparse
import csv
import io
import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, text

from app.config import settings
from app.etl.openstat import to_long
from app.etl.registry import SeriesKey, freeze_hash
from app.services.attribution import STANDARD_MODIFICATIONS, render

PROVINCE = {"code": "1401100000", "name": "Benguet"}


def is_benguet(value: str) -> bool:
    """Match PSA's plain `Benguet` and its hierarchical `....Benguet` label."""
    return value.strip().lstrip(".").strip().casefold() == "benguet"


def quarterly_period(raw: str) -> date:
    """Resolve PSA's year/quarter display labels without guessing a month."""
    text = raw.strip().casefold()
    year = re.search(r"\b(20\d{2})\b", text)
    quarter = re.search(r"(?:q(?:uarter)?\s*|\b)([1-4])(?:st|nd|rd|th)?\s*(?:quarter)?\b", text)
    if not year or not quarter:
        raise ValueError(f"Expected a year-and-quarter column, received {raw!r}")
    return date(int(year.group(1)), 1 + (int(quarter.group(1)) - 1) * 3, 1)


def next_quarter(value: date) -> date:
    return date(value.year + (value.month == 10), 1 if value.month == 10 else value.month + 3, 1)


def parse_openstat_export(payload: bytes) -> tuple[list[str], list[list[str]]]:
    """Read a downloaded PXWeb CSV, including its one-line title preamble."""
    rows = [row for row in csv.reader(io.StringIO(payload.decode("utf-8-sig"))) if any(cell.strip() for cell in row)]
    if len(rows) < 2:
        raise ValueError("OpenSTAT CSV has no header and data rows")
    # PSA exports place the table title on its own first row.
    if len(rows[0]) == 1 and len(rows[1]) > 2:
        rows = rows[1:]
    return [cell.strip() for cell in rows[0]], rows[1:]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variable", choices=("production", "area_harvested"), required=True)
    parser.add_argument("--table", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--unit", required=True, help="e.g. metric tons or hectares")
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--source-url", default="https://openstat.psa.gov.ph/")
    parser.add_argument("--key-columns", type=int, default=2)
    args = parser.parse_args()

    payload = args.csv.read_bytes()
    header, rows = parse_openstat_export(payload)
    values = to_long(header, rows, args.key_columns)
    if len(header) < 3:
        raise SystemExit("CSV has no annual value columns")
    # The first two columns are the selected geography and commodity under the
    # documented OpenSTAT production/area extracts. Keep only Benguet rows;
    # comparing case-insensitively tolerates PSA's display casing.
    try:
        geography_key = next(key for key in header if key.strip().casefold() == "geolocation")
        commodity_key = next(key for key in header if key.strip().casefold() in ("crop", "commodity"))
    except StopIteration as exc:
        raise SystemExit("Expected Crop/Commodity and Geolocation columns in the OpenSTAT CSV.") from exc
    selected = [
        row for row in values
        if is_benguet(row[geography_key]) and row[commodity_key].strip()
    ]
    if not selected:
        raise SystemExit("No Benguet rows found. Check --key-columns and the selected OpenSTAT CSV.")
    print(f"Preparing {len(selected)} Benguet crop rows from {args.csv.name}...", flush=True)

    checksum = hashlib.sha256(payload).hexdigest()
    retrieved = args.csv.stat().st_mtime
    from datetime import datetime, timezone
    retrieved_at = datetime.fromtimestamp(retrieved, timezone.utc).isoformat()
    attribution = render(args.table, args.title, retrieved_at, STANDARD_MODIFICATIONS)
    engine = create_engine(settings.database_url)

    grouped: dict[str, list[tuple[date, str]]] = {}
    for row in selected:
        # The export also contains Annual totals. They remain in the raw CSV,
        # but the dashboard's quarterly series must not double-count them.
        try:
            period = quarterly_period(row["period"])
        except ValueError:
            continue
        grouped.setdefault(row[commodity_key].strip(), []).append((period, row["value"].strip()))
    if not grouped:
        raise SystemExit("No quarterly columns found. Export Quarter1–Quarter4 from OpenSTAT.")

    print(f"Connecting to Neon and saving {len(grouped)} quarterly series...", flush=True)
    with engine.begin() as conn:
        extract_id = conn.execute(text("""
            INSERT INTO source_extract
              (source_table, source_table_title, source_url, selected_dimensions,
               retrieved_at, reference_period, vintage, raw_checksum, raw_path,
               permitted_use, source_attribution)
            VALUES (:table, :title, :url, CAST(:dimensions AS JSONB),
                    CAST(:retrieved AS TIMESTAMPTZ), :period, :vintage, :checksum,
                    :path, 'CC BY 4.0', :attribution)
            ON CONFLICT (source_table, raw_checksum) DO UPDATE
              SET vintage = EXCLUDED.vintage
            RETURNING extract_id
        """), {
            "table": args.table, "title": args.title, "url": args.source_url,
            "dimensions": json.dumps({"Geolocation": ["Benguet"]}),
            "retrieved": retrieved_at, "period": "quarterly", "vintage": retrieved_at[:7],
            "checksum": checksum, "path": str(args.csv.resolve()), "attribution": attribution.text,
        }).scalar_one()

        for commodity, points in grouped.items():
            key = SeriesKey(commodity, args.variable, PROVINCE["code"], "quarterly", args.unit)
            published = [period for period, raw in points if raw not in ("", "..")]
            conn.execute(text("""
                INSERT INTO series (series_id, commodity, variable, geography_code,
                  geography_name, geography_level, frequency, unit, extract_id, frozen_at, frozen_hash, notes)
                VALUES (:sid, :commodity, :variable, :code, :name, 'province', 'quarterly', :unit,
                  :extract_id, now(), :frozen_hash, 'PSA quarterly province-level crop statistic.')
                ON CONFLICT (series_id) DO UPDATE SET extract_id = EXCLUDED.extract_id,
                  frozen_at = EXCLUDED.frozen_at, frozen_hash = EXCLUDED.frozen_hash
            """), {"sid": key.series_id, "commodity": commodity, "variable": args.variable,
                  "code": PROVINCE["code"], "name": PROVINCE["name"], "unit": args.unit,
                  "extract_id": extract_id, "frozen_hash": freeze_hash(published)})
            observation_rows = []
            for period, raw in points:
                value = float(raw) if raw not in ("", "..") else None
                observation_rows.append({
                    "sid": key.series_id, "start": period, "end": next_quarter(period),
                    "value": value, "missing_reason": "absent" if value is None else None,
                })
            # Execute the commodity's rows together. This avoids a network round
            # trip to Neon for every individual quarter.
            conn.execute(text("""
                    INSERT INTO observation (series_id, period_start, period_end, original_value,
                      curated_value, missing_reason, quality_flag)
                    VALUES (:sid, :start, :end, :value, :value,
                      :missing_reason, 'ok')
                    ON CONFLICT (series_id, period_start) DO UPDATE SET
                      original_value = EXCLUDED.original_value, curated_value = EXCLUDED.curated_value,
                      missing_reason = EXCLUDED.missing_reason
                """), observation_rows)
    print(f"Finished {args.variable}: {len(grouped)} series saved.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
