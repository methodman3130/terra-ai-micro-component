"""Load PSGC municipal boundaries into PostGIS.

Source: https://github.com/altcoder/philippines-psgc-shapefiles (MIT),
Level 3 (municipalities and cities), PSGC vintage 31 December 2023.

The CRS check is not optional. That repository's README calls the files WGS84
but also mentions EPSG:32651 (UTM 51N). Loading a UTM file as if it were
lat/long puts Benguet somewhere in the Gulf of Guinea, and the map still
renders — it just renders wrongly. So: read the declared CRS, refuse to guess,
and reproject explicitly to EPSG:4326.

Usage:
    python scripts/load_psgc.py path/to/Regions.shp.zip --province 1411
"""
from __future__ import annotations

import argparse
import sys

TARGET_EPSG = 4326
BENGUET = "1411"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("shapefile", help="Path to the Level 3 shapefile or .shp.zip")
    parser.add_argument("--province", default=BENGUET, help="PSGC province code filter")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    try:
        import geopandas as gpd
    except ImportError:
        print(
            "geopandas is required for this loader.\n"
            "  pip install geopandas\n"
            "Alternatively use ogr2ogr:\n"
            "  ogr2ogr -f PostgreSQL PG:'...' input.shp -t_srs EPSG:4326 -nln municipality_raw",
            file=sys.stderr,
        )
        return 2

    gdf = gpd.read_file(args.shapefile)

    if gdf.crs is None:
        print(
            "ERROR: the shapefile declares no CRS. Refusing to assume one.\n"
            "Inspect the .prj file and pass the data through ogr2ogr with an "
            "explicit -s_srs before loading.",
            file=sys.stderr,
        )
        return 1

    print(f"declared CRS: {gdf.crs.to_string()}")
    if gdf.crs.to_epsg() != TARGET_EPSG:
        print(f"reprojecting {gdf.crs.to_epsg()} -> {TARGET_EPSG}")
        gdf = gdf.to_crs(epsg=TARGET_EPSG)

    # Sanity check: Benguet sits near 16.4N, 120.6E. If the centroid is nowhere
    # near the Philippines, the CRS handling went wrong and loading would be worse
    # than failing.
    bounds = gdf.total_bounds  # minx, miny, maxx, maxy
    if not (115 < bounds[0] < 128 and 4 < bounds[1] < 22):
        print(
            f"ERROR: bounds {bounds} are not in the Philippines. "
            "The CRS is being mishandled; aborting rather than loading wrong geometry.",
            file=sys.stderr,
        )
        return 1

    code_column = next(
        (c for c in ("adm3_psgc", "ADM3_PCODE", "psgc_code", "PSGC") if c in gdf.columns), None
    )
    if code_column is None:
        print(f"ERROR: no PSGC code column found. Columns: {list(gdf.columns)}", file=sys.stderr)
        return 1

    gdf["psgc_code"] = gdf[code_column].astype(str).str.replace(r"^PH", "", regex=True)
    subset = gdf[gdf["psgc_code"].str.startswith(args.province)]
    print(f"{len(subset)} municipalities match province {args.province}")

    if args.dry_run:
        print(subset[["psgc_code"]].head(20).to_string())
        return 0

    from sqlalchemy import create_engine
    from app.config import settings

    engine = create_engine(settings.database_url)
    subset = subset.rename(columns={"adm3_en": "name", "ADM3_EN": "name"})
    subset["province_code"] = args.province
    subset["psgc_vintage"] = "2023-12-31"
    subset["source_note"] = "altcoder/philippines-psgc-shapefiles (MIT), reprojected to EPSG:4326"
    subset.to_postgis("municipality_staging", engine, if_exists="replace", index=False)
    print("loaded into municipality_staging — review, then INSERT into municipality")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
