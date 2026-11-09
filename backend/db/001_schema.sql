-- TERRA-AI Micro-Component — curated schema
-- PostgreSQL 16+ / PostGIS 3.4+ (validated against PostGIS 3.6.0)
--
-- Design rules enforced here, not in application code:
--   1. Every observation carries its provenance and its CC BY attribution string.
--   2. Raw values are never overwritten. curated_value sits beside original_value.
--   3. A series must be registered (and frozen) before it can be scored.
--   4. Geometry is municipal grain. There is no farm-parcel polygon table, because
--      no such public layer exists for Benguet (see market research, 5 Nov 2026).

CREATE EXTENSION IF NOT EXISTS postgis;

-- ---------------------------------------------------------------------------
-- Provenance
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS source_extract (
    extract_id        BIGSERIAL PRIMARY KEY,
    source_table      TEXT        NOT NULL,          -- e.g. 0032M4AFN06
    source_table_title TEXT       NOT NULL,
    source_url        TEXT        NOT NULL,
    selected_dimensions JSONB     NOT NULL,          -- exactly what was requested
    retrieved_at      TIMESTAMPTZ NOT NULL,
    reference_period  TEXT        NOT NULL,
    release_date      DATE,                          -- NULL when PSA does not publish one
    vintage           TEXT        NOT NULL,          -- retrieval vintage label
    raw_checksum      CHAR(64)    NOT NULL,          -- SHA-256 of the immutable raw file
    raw_path          TEXT        NOT NULL,
    permitted_use     TEXT        NOT NULL DEFAULT 'CC BY 4.0',
    source_attribution TEXT       NOT NULL,          -- rendered credit line, travels with exports
    UNIQUE (source_table, raw_checksum)
);

COMMENT ON COLUMN source_extract.source_attribution IS
  'Full CC BY credit line. Required on every view and export. Never render a series without it.';

-- ---------------------------------------------------------------------------
-- Series register — frozen before any development comparison
-- ---------------------------------------------------------------------------

CREATE TYPE series_frequency AS ENUM ('annual', 'quarterly', 'monthly', 'daily');

CREATE TABLE IF NOT EXISTS series (
    series_id      TEXT PRIMARY KEY,                 -- deterministic, see etl/registry.py
    commodity      TEXT NOT NULL,
    variable       TEXT NOT NULL,                    -- farmgate_price | production | area_harvested
    geography_code TEXT NOT NULL,                    -- PSGC code
    geography_name TEXT NOT NULL,
    geography_level TEXT NOT NULL
        CHECK (geography_level IN ('country','region','province','municipality')),
    frequency      series_frequency NOT NULL,
    unit           TEXT NOT NULL,
    grade_variety  TEXT,
    extract_id     BIGINT NOT NULL REFERENCES source_extract(extract_id),
    frozen_at      TIMESTAMPTZ,                      -- NULL = still mutable
    frozen_hash    CHAR(64),                         -- hash of the ordered observation keys
    notes          TEXT
);

CREATE INDEX IF NOT EXISTS series_lookup
    ON series (commodity, variable, geography_code, frequency);

-- ---------------------------------------------------------------------------
-- Observations — original preserved, curated derived
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS observation (
    series_id      TEXT NOT NULL REFERENCES series(series_id) ON DELETE CASCADE,
    period_start   DATE NOT NULL,
    period_end     DATE NOT NULL,
    original_value NUMERIC,                          -- NULL where the source is blank/suppressed
    curated_value  NUMERIC,                          -- NULL where cleaning could not resolve it
    missing_reason TEXT,                             -- 'absent' | 'suppressed' | 'invalid' | NULL
    quality_flag   TEXT NOT NULL DEFAULT 'ok'
        CHECK (quality_flag IN ('ok','imputed','revised','suspect','unit_change','definition_change')),
    rule_id        TEXT,                             -- which cleaning rule touched it
    PRIMARY KEY (series_id, period_start)
);

CREATE INDEX IF NOT EXISTS observation_period ON observation (series_id, period_start DESC);

-- Forecast targets must be original observations. This view is what the harness reads.
CREATE OR REPLACE VIEW observation_scoreable AS
SELECT series_id, period_start, period_end, original_value AS value, quality_flag
FROM observation
WHERE original_value IS NOT NULL;

COMMENT ON VIEW observation_scoreable IS
  'Forecast targets. Imputed values are deliberately excluded: never score against a filled gap.';

-- ---------------------------------------------------------------------------
-- Cleaning audit — every transformation is reconstructable
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS cleaning_run (
    run_id         BIGSERIAL PRIMARY KEY,
    rule_id        TEXT NOT NULL,
    script_version TEXT NOT NULL,
    input_checksum  CHAR(64) NOT NULL,
    output_checksum CHAR(64) NOT NULL,
    rows_affected  INTEGER NOT NULL,
    rationale      TEXT NOT NULL,
    ran_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Geography — municipal grain only
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS municipality (
    psgc_code    TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    province_code TEXT NOT NULL,
    province_name TEXT NOT NULL,
    region_code  TEXT NOT NULL,
    psgc_vintage DATE NOT NULL,                      -- boundary vintage, not data vintage
    source_note  TEXT NOT NULL,
    geom         geometry(MultiPolygon, 4326) NOT NULL
);

CREATE INDEX IF NOT EXISTS municipality_geom ON municipality USING GIST (geom);
CREATE INDEX IF NOT EXISTS municipality_province ON municipality (province_code);

-- Schema exists so field geocoding has somewhere to land under the funded phase.
-- It is intentionally EMPTY in the micro-component: no public farm-point data exists.
CREATE TABLE IF NOT EXISTS site_point (
    site_id      BIGSERIAL PRIMARY KEY,
    site_type    TEXT NOT NULL
        CHECK (site_type IN ('trading_post','cold_storage','consented_farm','weather_station','soil_node')),
    label        TEXT,
    psgc_code    TEXT REFERENCES municipality(psgc_code),
    precision_m  INTEGER,                            -- coarsened location for consented farms
    restricted   BOOLEAN NOT NULL DEFAULT TRUE,      -- exact farm coordinates stay restricted
    geom         geometry(Point, 4326) NOT NULL
);

CREATE INDEX IF NOT EXISTS site_point_geom ON site_point USING GIST (geom);

-- ---------------------------------------------------------------------------
-- Benchmark results — preregistration lives in the database
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS benchmark_protocol (
    protocol_id    BIGSERIAL PRIMARY KEY,
    label          TEXT NOT NULL UNIQUE,
    declared_box   JSONB NOT NULL,                   -- p,q,P,Q,d,D limits and allowed m
    horizons       INTEGER[] NOT NULL,
    min_train      INTEGER NOT NULL,
    final_window_start DATE NOT NULL,
    final_window_end   DATE NOT NULL,
    software_versions JSONB NOT NULL,
    frozen_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS benchmark_score (
    score_id     BIGSERIAL PRIMARY KEY,
    protocol_id  BIGINT NOT NULL REFERENCES benchmark_protocol(protocol_id),
    series_id    TEXT   NOT NULL REFERENCES series(series_id),
    model        TEXT   NOT NULL,
    horizon      INTEGER NOT NULL,
    n_origins    INTEGER NOT NULL,
    mase         DOUBLE PRECISION,
    mae          DOUBLE PRECISION,
    rmse         DOUBLE PRECISION,
    bias         DOUBLE PRECISION,
    engine       TEXT NOT NULL,                      -- 'statsforecast' | 'statsmodels'
    scored_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (protocol_id, series_id, model, horizon, engine)
);

COMMENT ON COLUMN benchmark_score.engine IS
  'Two engines score the same protocol. Disagreement between them is a finding, not an error to hide.';
