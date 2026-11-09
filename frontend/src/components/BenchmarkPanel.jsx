/**
 * Benchmark results.
 *
 * The baselines are listed first and visually marked, because the question the
 * table has to answer is "did anything beat them", not "which row has the
 * smallest number". A MASE under 1 is shown without a win badge: the caveat
 * from the API is rendered verbatim underneath.
 */
const BASELINES = new Set(["RandomWalk", "SeasonalNaive"]);

function fmt(v, digits = 3) {
  return v === null || v === undefined ? "—" : Number(v).toFixed(digits);
}

export default function BenchmarkPanel({ payload, error }) {
  if (error) {
    return (
      <div className="rounded-lg border border-slate-200 p-4 text-sm text-slate-500">
        No scores recorded for this series yet. Run the harness first — an empty
        benchmark is an honest state, not a failure.
      </div>
    );
  }
  if (!payload) return null;

  const { scores, interpretation } = payload;
  const ordered = [...scores].sort((a, b) => {
    if (a.horizon !== b.horizon) return a.horizon - b.horizon;
    const ab = BASELINES.has(a.model) ? 0 : 1;
    const bb = BASELINES.has(b.model) ? 0 : 1;
    return ab - bb || a.model.localeCompare(b.model);
  });

  return (
    <div className="rounded-lg border border-slate-200 p-4">
      <h2 className="mb-3 text-base font-semibold text-slate-800">Walk-forward benchmark</h2>

      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-slate-200 text-left text-slate-500">
              <th className="py-1 pr-3">model</th>
              <th className="py-1 pr-3">h</th>
              <th className="py-1 pr-3">origins</th>
              <th className="py-1 pr-3">MASE</th>
              <th className="py-1 pr-3">MAE</th>
              <th className="py-1 pr-3">RMSE</th>
              <th className="py-1 pr-3">bias</th>
              <th className="py-1">engine</th>
            </tr>
          </thead>
          <tbody>
            {ordered.map((r) => (
              <tr
                key={`${r.model}-${r.horizon}-${r.engine}`}
                className={BASELINES.has(r.model) ? "bg-slate-50" : ""}
              >
                <td className="py-1 pr-3 font-medium text-slate-800">
                  {r.model}
                  {BASELINES.has(r.model) && (
                    <span className="ml-1 rounded bg-slate-200 px-1 text-[10px] text-slate-600">
                      baseline
                    </span>
                  )}
                </td>
                <td className="py-1 pr-3">{r.horizon}</td>
                <td className="py-1 pr-3">{r.n_origins}</td>
                <td className="py-1 pr-3">{fmt(r.mase)}</td>
                <td className="py-1 pr-3">{fmt(r.mae, 2)}</td>
                <td className="py-1 pr-3">{fmt(r.rmse, 2)}</td>
                <td className="py-1 pr-3">{fmt(r.bias, 2)}</td>
                <td className="py-1 text-slate-500">{r.engine}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-3 space-y-1 text-[11px] leading-snug text-slate-500">
        <p>{interpretation.mase_caveat}</p>
        <p>{interpretation.bias_sign}</p>
        {!interpretation.seasonal_naive_independent && (
          <p className="text-amber-700">
            Annual series: seasonal naive would duplicate the random walk, so it is not
            reported as an independent second baseline.
          </p>
        )}
        <p>
          Beat all baselines on MAE:{" "}
          <span className="font-medium text-slate-700">
            {interpretation.beats_all_baselines_on_mae.length
              ? interpretation.beats_all_baselines_on_mae.join(", ")
              : "nothing"}
          </span>
        </p>
        {interpretation.cross_checked_models.length > 0 && (
          <p>Cross-checked across two engines: {interpretation.cross_checked_models.join(", ")}</p>
        )}
      </div>
    </div>
  );
}
