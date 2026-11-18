/**
 * Forecasting for the farmer view.
 *
 * The research panels in this app deliberately issue no forecast. The farmer
 * view must, because "should I harvest now or in three weeks" is not a question
 * that retrospective scores answer. The compromise is that every number this
 * module produces carries its own back-tested error band, computed here from
 * the same series, so the view can show how wrong it has been before rather
 * than asserting a point estimate.
 *
 * Model: multiplicative seasonality (month-of-year median deviation from a
 * centred rolling level, in logs) plus a damped linear drift on the
 * deseasonalised level. Intervals are empirical quantiles of walk-forward
 * residuals at the same horizon — not Gaussian, because these residuals are
 * not Gaussian.
 */

const MIN_TRAIN = 72; // six years before the first back-test origin

/** Zero is PSA's "no observation" sentinel here, not a price of nothing. */
export function toLogSeries(observations) {
  const rows = observations
    .map((o) => ({
      t: monthIndex(o.period_start),
      v: o.original_value === null ? null : Number(o.original_value),
      flag: o.quality_flag,
    }))
    .filter((r) => Number.isFinite(r.t))
    .sort((a, b) => a.t - b.t);
  if (!rows.length) return null;
  const t0 = rows[0].t;
  const n = rows[rows.length - 1].t - t0 + 1;
  const L = new Array(n).fill(null);
  const V = new Array(n).fill(null);
  for (const r of rows) {
    if (r.v === null || r.v === 0) continue;
    V[r.t - t0] = r.v;
    L[r.t - t0] = Math.log(r.v);
  }
  return { L, V, t0, n };
}

export function monthIndex(isoDate) {
  const d = new Date(String(isoDate).slice(0, 10) + "T00:00:00Z");
  if (Number.isNaN(d.getTime())) return NaN;
  return d.getUTCFullYear() * 12 + d.getUTCMonth();
}
export function fromMonthIndex(t) {
  return { y: Math.floor(t / 12), m: (t % 12) + 1 };
}

function median(a) {
  if (!a.length) return 0;
  const s = [...a].sort((x, y) => x - y);
  const h = Math.floor(s.length / 2);
  return s.length % 2 ? s[h] : (s[h - 1] + s[h]) / 2;
}

/** Month-of-year deviation from a centred 13-month mean, in logs. */
function seasonalIndex(L, upto, t0) {
  const dev = Array.from({ length: 12 }, () => []);
  for (let i = 0; i < upto; i += 1) {
    if (L[i] === null) continue;
    const w = [];
    for (let j = Math.max(0, i - 6); j < Math.min(upto, i + 7); j += 1) {
      if (L[j] !== null) w.push(L[j]);
    }
    if (w.length < 8) continue;
    dev[(t0 + i) % 12].push(L[i] - w.reduce((a, b) => a + b, 0) / w.length);
  }
  const s = dev.map((d) => (d.length >= 3 ? median(d) : 0));
  const mu = s.reduce((a, b) => a + b, 0) / 12;
  return s.map((x) => x - mu);
}

function level(L, upto, t0, k = 18) {
  const s = seasonalIndex(L, upto, t0);
  let pts = [];
  for (let i = Math.max(0, upto - k); i < upto; i += 1) {
    if (L[i] !== null) pts.push([i, L[i] - s[(t0 + i) % 12]]);
  }
  if (pts.length < 4) {
    pts = [];
    for (let i = 0; i < upto; i += 1) if (L[i] !== null) pts.push([i, L[i]]);
    pts = pts.slice(-6);
  }
  const n = pts.length || 1;
  const mx = pts.reduce((a, p) => a + p[0], 0) / n;
  const my = pts.reduce((a, p) => a + p[1], 0) / n;
  const den = pts.reduce((a, p) => a + (p[0] - mx) ** 2, 0) || 1;
  const slope = pts.reduce((a, p) => a + (p[0] - mx) * (p[1] - my), 0) / den;
  return { my, mx, slope, s };
}

/** Log-space point forecasts for horizons 1..H from origin `upto`. */
function forecastLog(L, upto, t0, H, damp = 0.8) {
  const { my, mx, slope, s } = level(L, upto, t0);
  const out = [];
  for (let h = 1; h <= H; h += 1) {
    const t = upto - 1 + h;
    let d = 0;
    if (t > mx) for (let j = 1; j <= Math.round(t - mx); j += 1) d += slope * damp ** j;
    d = Math.max(-0.5, Math.min(0.5, d)); // a damped drift that still explodes is a bug, not a signal
    out.push(my + d + s[(t0 + t) % 12]);
  }
  return out;
}

function quantile(sorted, q) {
  if (!sorted.length) return 0;
  const k = (sorted.length - 1) * q;
  const lo = Math.floor(k);
  const hi = Math.min(lo + 1, sorted.length - 1);
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (k - lo);
}

/** Walk-forward residuals, plus the two naive baselines we have to beat. */
function backtest(L, t0, H) {
  const n = L.length;
  const res = Array.from({ length: H + 1 }, () => []);
  const rw = Array.from({ length: H + 1 }, () => []);
  const sn = Array.from({ length: H + 1 }, () => []);
  for (let o = MIN_TRAIN; o < n; o += 1) {
    let any = false;
    for (let i = Math.max(0, o - 12); i < o; i += 1) if (L[i] !== null) any = true;
    if (!any) continue;
    const f = forecastLog(L, o, t0, H);
    let last = null;
    for (let i = o - 1; i >= 0; i -= 1) if (L[i] !== null) { last = L[i]; break; }
    for (let h = 1; h <= H; h += 1) {
      const t = o - 1 + h;
      if (t >= n || L[t] === null) continue;
      res[h].push(L[t] - f[h - 1]);
      if (last !== null) rw[h].push(L[t] - last);
      if (t - 12 >= 0 && L[t - 12] !== null) sn[h].push(L[t] - L[t - 12]);
    }
  }
  return { res, rw, sn };
}

const mae = (a) => (a.length ? a.reduce((x, y) => x + Math.abs(y), 0) / a.length : null);

/**
 * Build the farmer-view forecast for one observation payload.
 * Returns null when the series is too short to back-test honestly.
 */
export function buildForecast(observations, { H = 18 } = {}) {
  const S = toLogSeries(observations ?? []);
  if (!S) return null;
  const { L, V, t0, n } = S;
  let lastIdx = -1;
  for (let i = n - 1; i >= 0; i -= 1) if (L[i] !== null) { lastIdx = i; break; }
  if (lastIdx < MIN_TRAIN) return null;

  const HB = Math.min(12, H);
  const { res, rw, sn } = backtest(L, t0, HB);
  const f = forecastLog(L, lastIdx + 1, t0, H);

  const months = [];
  for (let h = 1; h <= H; h += 1) {
    const e = [...res[Math.min(h, HB)]].sort((a, b) => a - b);
    if (!e.length) break;
    const { y, m } = fromMonthIndex(t0 + lastIdx + h);
    const p = Math.exp(f[h - 1]);
    months.push({
      y, m, h,
      p: round2(p),
      lo: round2(Math.exp(f[h - 1] + quantile(e, 0.1))),
      hi: round2(Math.exp(f[h - 1] + quantile(e, 0.9))),
      lo50: round2(Math.exp(f[h - 1] + quantile(e, 0.25))),
      hi50: round2(Math.exp(f[h - 1] + quantile(e, 0.75))),
    });
  }

  const scores = {};
  for (const h of [1, 3, 6, 12]) {
    if (h > HB) continue;
    scores[h] = { model: mae(res[h]), rw: mae(rw[h]), sn: mae(sn[h]), n: res[h].length };
  }

  const si = seasonalIndex(L, lastIdx + 1, t0);
  const seasonal = {};
  for (let m = 1; m <= 12; m += 1) seasonal[m] = Math.exp(si[(m - 1) % 12]);

  const hist = [];
  for (let i = 0; i < n; i += 1) {
    if (V[i] === null) continue;
    const { y, m } = fromMonthIndex(t0 + i);
    hist.push({ y, m, v: V[i] });
  }
  const lastP = fromMonthIndex(t0 + lastIdx);

  return {
    hist, fc: months, scores, seasonal,
    lastObs: { y: lastP.y, m: lastP.m, v: V[lastIdx] },
    nObs: hist.length,
    missing: n - hist.length,
  };
}

const round2 = (x) => Math.round(x * 100) / 100;

/** Monotone cubic (Fritsch–Carlson). Shape only — see the warning in the view. */
export function monotoneCubic(points) {
  const n = points.length;
  if (n < 2) return () => (n ? points[0].y : 0);
  const xs = points.map((p) => p.x);
  const ys = points.map((p) => p.y);
  const d = [];
  for (let i = 0; i < n - 1; i += 1) d.push((ys[i + 1] - ys[i]) / (xs[i + 1] - xs[i]));
  const m = new Array(n);
  m[0] = d[0];
  m[n - 1] = d[n - 2];
  for (let i = 1; i < n - 1; i += 1) m[i] = d[i - 1] * d[i] <= 0 ? 0 : (d[i - 1] + d[i]) / 2;
  for (let i = 0; i < n - 1; i += 1) {
    if (d[i] === 0) { m[i] = 0; m[i + 1] = 0; continue; }
    const a = m[i] / d[i];
    const b = m[i + 1] / d[i];
    const ss = a * a + b * b;
    if (ss > 9) { const tt = 3 / Math.sqrt(ss); m[i] = tt * a * d[i]; m[i + 1] = tt * b * d[i]; }
  }
  return (x) => {
    if (x <= xs[0]) return ys[0];
    if (x >= xs[n - 1]) return ys[n - 1];
    let i = 0;
    while (x > xs[i + 1]) i += 1;
    const h = xs[i + 1] - xs[i];
    const s = (x - xs[i]) / h;
    const s2 = s * s;
    const s3 = s2 * s;
    return (2 * s3 - 3 * s2 + 1) * ys[i] + (s3 - 2 * s2 + s) * h * m[i]
      + (-2 * s3 + 3 * s2) * ys[i + 1] + (s3 - s2) * h * m[i + 1];
  };
}
