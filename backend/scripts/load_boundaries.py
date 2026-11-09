"""Load Benguet municipal boundaries into PostGIS.

Source: faeldon/philippines-json-maps, `latest/geojson/provdists/medres/
municities-provdist-1401100000.0.01.json` — municipalities and cities of
Benguet (adm2_psgc 1401100000), built 2026-11-07 from PSGC 2026-3q, itself
derived from altcoder/philippines-psgc-shapefiles v1.0.1 (OCHA source).

Note on the PSGC code: Benguet is **1401100000**, not 1411000000. The province
digits sit in positions 3-5 of the ten-digit code, so a code assembled by
concatenating region and province numbers is wrong and 404s against this
dataset. Codes are read from the data, never constructed.

Geometry is already EPSG:4326 lat/long. The bounds assertion below is not
ceremony: a mishandled CRS still renders a map, just the wrong one.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, text

from app.config import settings

PROVINCE_CODE = "1401100000"
PROVINCE_NAME = "Benguet"
REGION_CODE = "1400000000"
PSGC_VINTAGE = "2026-09-30"  # PSGC 2026 Q3, per the dataset manifest
SOURCE_NOTE = (
    "faeldon/philippines-json-maps latest/geojson/provdists/medres "
    "municities-provdist-1401100000.0.01.json (PSGC 2026-3q, built 2026-11-07); "
    "upstream altcoder/philippines-psgc-shapefiles v1.0.1, OCHA source. EPSG:4326."
)

# Benguet sits roughly 16.2-17.0 N, 120.4-121.0 E.
PH_BOUNDS = (115.0, 4.0, 128.0, 22.0)


def main() -> int:
    if len(sys.argv) < 2:
        print(f"usage: {sys.argv[0]} <benguet-municities.geojson>", file=sys.stderr)
        return 2

    data = json.loads(Path(sys.argv[1]).read_text())
    features = data.get("features", [])
    if not features:
        print("ERROR: no features in file", file=sys.stderr)
        return 1

    xs, ys = [], []
    for f in features:
        def walk(coords):
            if isinstance(coords[0], (int, float)):
                xs.append(coords[0])
                ys.append(coords[1])
            else:
                for c in coords:
                    walk(c)
        walk(f["geometry"]["coordinates"])

    bounds = (min(xs), min(ys), max(xs), max(ys))
    print(f"bounds: {tuple(round(b, 3) for b in bounds)}")
    if not (PH_BOUNDS[0] < bounds[0] and bounds[2] < PH_BOUNDS[2]
            and PH_BOUNDS[1] < bounds[1] and bounds[3] < PH_BOUNDS[3]):
        print("ERROR: bounds are not in the Philippines; aborting rather than "
              "loading wrong geometry.", file=sys.stderr)
        return 1

    engine = create_engine(settings.database_url)
    loaded = 0
    with engine.begin() as conn:
        # The placeholder province rectangle from the seed load must go, or it
        # would sit under the real polygons and double-count every join.
        conn.execute(text("DELETE FROM municipality WHERE psgc_code = '1411000000'"))

        for f in features:
            props = f["properties"]
            conn.execute(
                text("""
                INSERT INTO municipality (psgc_code, name, province_code, province_name,
                                          region_code, psgc_vintage, source_note, geom)
                VALUES (:code, :name, :pcode, :pname, :rcode, CAST(:vintage AS DATE), :note,
                        ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(:geom), 4326)))
                ON CONFLICT (psgc_code) DO UPDATE
                  SET name = EXCLUDED.name, geom = EXCLUDED.geom,
                      psgc_vintage = EXCLUDED.psgc_vintage, source_note = EXCLUDED.source_note
                """),
                {
                    "code": str(props["adm3_psgc"]),
                    "name": props["adm3_en"],
                    # Baguio is an independent chartered city carried in this file;
                    # it keeps its own adm2 code so provincial joins stay honest.
                    "pcode": PROVINCE_CODE if str(props["adm3_psgc"]).startswith("14011") else str(props["adm2_psgc"]),
                    "pname": PROVINCE_NAME if str(props["adm3_psgc"]).startswith("14011") else props["adm3_en"],
                    "rcode": REGION_CODE,
                    "vintage": PSGC_VINTAGE,
                    "note": SOURCE_NOTE,
                    "geom": json.dumps(f["geometry"]),
                },
            )
            loaded += 1

        valid = conn.execute(
            text("SELECT count(*) FROM municipality WHERE NOT ST_IsValid(geom)")
        ).scalar_one()

    print(f"loaded {loaded} polygons; invalid geometries: {valid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
