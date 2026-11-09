-- Per-origin forecast records.
--
-- Two protocol requirements need these, and neither can be met from aggregate
-- scores alone:
--
--   1. "Comparable origins - compare methods on the same crop, geography,
--      horizon and available target dates." Methods with different minimum
--      training windows (SARIMA needs 96 monthly observations, the others 60)
--      score different numbers of origins, so their aggregate MAEs are not
--      paired and must not be differenced directly.
--   2. The prototype's benchmark view must "show model, origin, horizon,
--      actual, prediction, errors, score denominator".

CREATE TABLE IF NOT EXISTS benchmark_origin (
    protocol_id  BIGINT NOT NULL REFERENCES benchmark_protocol(protocol_id),
    series_id    TEXT   NOT NULL REFERENCES series(series_id) ON DELETE CASCADE,
    model        TEXT   NOT NULL,
    horizon      INTEGER NOT NULL,
    origin_period DATE  NOT NULL,
    target_period DATE  NOT NULL,
    forecast     DOUBLE PRECISION NOT NULL,
    actual       DOUBLE PRECISION NOT NULL,
    error        DOUBLE PRECISION NOT NULL,   -- forecast - actual
    scale_q      DOUBLE PRECISION,            -- q_t; NULL = undefined at this origin
    PRIMARY KEY (protocol_id, series_id, model, horizon, origin_period)
);

CREATE INDEX IF NOT EXISTS benchmark_origin_lookup
    ON benchmark_origin (series_id, horizon, target_period);
