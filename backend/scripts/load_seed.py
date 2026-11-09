"""Load the retrieved PSA farmgate panel into the curated schema.

Cleaning rules applied here, each recorded in ``cleaning_run``:

  R1  blank -> original_value NULL, missing_reason 'absent'
      PSA has not published that month. Not imputed, not zero.
  R2  0.00  -> original_value kept as published, quality_flag 'suspect'
      A zero farmgate price is not a real price. The published figure is
      preserved (we do not edit the source) but it is flagged, and the
      scoreable view excludes suspect points from forecast targets.

Nothing else is altered. No interpolation, no outlier removal: the 21x and 43x
price ranges in this panel are the phenomenon under study, not noise.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, text

from app.config import settings
from app.etl.registry import SeriesKey, freeze_hash
from app.services.attribution import STANDARD_MODIFICATIONS, render
from data_seed.benguet_farmgate_2010_2026 import (
    GEOGRAPHY, N_PERIODS, RETRIEVED_AT, SERIES, SOURCE, START_MONTH, START_YEAR, UNIT,
)

SCRIPT_VERSION = "load_seed/1.0.0"


def periods(n: int) -> list[date]:
    out, y, m = [], START_YEAR, START_MONTH
    for _ in range(n):
        out.append(date(y, m, 1))
        m += 1
        if m == 13:
            m, y = 1, y + 1
    return out


def month_end(d: date) -> date:
    return date(d.year + (d.month == 12), 1 if d.month == 12 else d.month + 1, 1)


def main() -> int:
    engine = create_engine(settings.database_url)
    all_periods = periods(N_PERIODS)
    counts = {"absent": 0, "suspect": 0, "ok": 0}

    with engine.begin() as conn:
        extract_ids: dict[str, int] = {}
        for key, meta in SOURCE.items():
            attribution = render(
                meta["table"], meta["title"], RETRIEVED_AT, STANDARD_MODIFICATIONS
            )
            row = conn.execute(
                text("""
                INSERT INTO source_extract
                  (source_table, source_table_title, source_url, selected_dimensions,
                   retrieved_at, reference_period, release_date, vintage, raw_checksum,
                   raw_path, permitted_use, source_attribution)
                VALUES
                  (:t, :title, :url, CAST(:dims AS JSONB), CAST(:ret AS TIMESTAMPTZ),
                   :ref, NULL, :vintage, :sum, :path, 'CC BY 4.0', :attr)
                ON CONFLICT (source_table, raw_checksum) DO UPDATE SET vintage = EXCLUDED.vintage
                RETURNING extract_id
                """),
                {
                    "t": meta["table"], "title": meta["title"], "url": meta["url"],
                    "dims": json.dumps({
                        "Geolocation": ["Benguet"],
                        "Commodity": [c for c, (_, s) in SERIES.items() if s == key],
                        "Year": ["2010-2026"], "Period": ["January-December"],
                    }),
                    "ret": RETRIEVED_AT, "ref": "2010-01..2026-12",
                    "vintage": RETRIEVED_AT[:7], "sum": meta["checksum"],
                    "path": f"browser-retrieval://{meta['table']}", "attr": attribution.text,
                },
            ).one()
            extract_ids[key] = row[0]

        conn.execute(
            text("""
            INSERT INTO municipality (psgc_code, name, province_code, province_name,
                                      region_code, psgc_vintage, source_note, geom)
            VALUES ('1411000000','Benguet (province extent)','1411','Benguet','14',
                    DATE '2023-12-31',
                    'Placeholder province extent. Replace with PSGC Level 3 municipal polygons.',
                    ST_Multi(ST_GeomFromText(
                      'POLYGON((120.30 16.20,120.95 16.20,120.95 16.95,120.30 16.95,120.30 16.20))',
                      4326)))
            ON CONFLICT (psgc_code) DO NOTHING
            """)
        )

        for commodity, (packed, source_key) in SERIES.items():
            fields = packed.split(",")
            if len(fields) != N_PERIODS:
                raise SystemExit(f"{commodity}: expected {N_PERIODS} slots, got {len(fields)}")

            key = SeriesKey(commodity, "farmgate_price", GEOGRAPHY["psgc_code"], "monthly", UNIT)
            published = [p for p, v in zip(all_periods, fields) if v.strip()]

            conn.execute(
                text("""
                INSERT INTO series (series_id, commodity, variable, geography_code,
                                    geography_name, geography_level, frequency, unit,
                                    grade_variety, extract_id, frozen_at, frozen_hash, notes)
                VALUES (:sid, :c, 'farmgate_price', :gc, :gn, 'province', 'monthly', :u,
                        NULL, :eid, now(), :fh,
                        'Province grain: PSA publishes farmgate prices at province level, not municipality.')
                ON CONFLICT (series_id) DO UPDATE
                  SET frozen_at = now(), frozen_hash = EXCLUDED.frozen_hash
                """),
                {
                    "sid": key.series_id, "c": commodity, "gc": GEOGRAPHY["psgc_code"],
                    "gn": GEOGRAPHY["name"], "u": UNIT, "eid": extract_ids[source_key],
                    "fh": freeze_hash(published),
                },
            )

            for period, raw in zip(all_periods, fields):
                raw = raw.strip()
                if not raw:
                    value, flag, reason, rule = None, "ok", "absent", "R1"
                    counts["absent"] += 1
                else:
                    value = float(raw)
                    if value == 0.0:
                        flag, reason, rule = "suspect", None, "R2"
                        counts["suspect"] += 1
                    else:
                        flag, reason, rule = "ok", None, None
                        counts["ok"] += 1
                conn.execute(
                    text("""
                    INSERT INTO observation (series_id, period_start, period_end,
                                             original_value, curated_value, missing_reason,
                                             quality_flag, rule_id)
                    VALUES (:sid, :ps, :pe, :v, :v, :mr, :qf, :rid)
                    ON CONFLICT (series_id, period_start) DO UPDATE
                      SET original_value = EXCLUDED.original_value,
                          quality_flag = EXCLUDED.quality_flag
                    """),
                    {
                        "sid": key.series_id, "ps": period, "pe": month_end(period),
                        "v": value, "mr": reason, "qf": flag, "rid": rule,
                    },
                )

        digest = hashlib.sha256(
            "|".join(f"{k}:{v}" for k, v in sorted(counts.items())).encode()
        ).hexdigest()
        for rule, rationale in (
            ("R1", "Blank period left NULL with missing_reason='absent'; never imputed."),
            ("R2", "Published 0.00 preserved but flagged 'suspect'; a zero farmgate price is not a price."),
        ):
            conn.execute(
                text("""
                INSERT INTO cleaning_run (rule_id, script_version, input_checksum,
                                          output_checksum, rows_affected, rationale)
                VALUES (:r, :v, :i, :o, :n, :why)
                """),
                {
                    "r": rule, "v": SCRIPT_VERSION,
                    "i": SOURCE["leafy"]["checksum"], "o": digest,
                    "n": counts["absent"] if rule == "R1" else counts["suspect"],
                    "why": rationale,
                },
            )

    print(f"loaded: {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
