-- Protocol measures the first schema did not carry.
--
-- The locked evaluation protocol requires relative skill reported separately
-- against each applicable naive method, and the count of origins whose MASE
-- scaling was undefined published rather than silently dropped.

ALTER TABLE benchmark_score ADD COLUMN IF NOT EXISTS skill_vs_random_walk   DOUBLE PRECISION;
ALTER TABLE benchmark_score ADD COLUMN IF NOT EXISTS skill_vs_seasonal_naive DOUBLE PRECISION;
ALTER TABLE benchmark_score ADD COLUMN IF NOT EXISTS n_undefined_scale      INTEGER NOT NULL DEFAULT 0;
ALTER TABLE benchmark_score ADD COLUMN IF NOT EXISTS min_train_used         INTEGER;

COMMENT ON COLUMN benchmark_score.skill_vs_random_walk IS
  '1 - candidate MAE / random-walk MAE on paired targets. NULL when undefined.';
COMMENT ON COLUMN benchmark_score.n_undefined_scale IS
  'Origins excluded from MASE because q_t was zero or below the protocol threshold.';
