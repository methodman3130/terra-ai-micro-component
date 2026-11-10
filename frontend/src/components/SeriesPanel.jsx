import {
  CartesianGrid, Line, LineChart, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis,
} from "recharts";

/**
 * Observation history for one series.
 *
 * Flagged points are drawn as separate markers rather than smoothed into the
 * line, so a reader can see where the record is imputed, revised or suspect
 * instead of having to trust that it is clean.
 */
export default function SeriesPanel({ payload }) {
  if (!payload) {
    return (
      <div className="rounded-lg border border-slate-200 p-6 text-sm text-slate-500">
        Select a municipality to load its series.
      </div>
    );
  }

  const { series, observations, quality, attribution } = payload;
  const data = observations.map((o) => ({
    period: o.period_start,
    periodLabel: o.period?.label ?? o.period_start,
    value: o.original_value === null ? null : Number(o.original_value),
    flagged: o.quality_flag !== "ok" && o.original_value !== null ? Number(o.original_value) : null,
    flag: o.quality_flag,
  }));

  return (
    <div className="rounded-lg border border-slate-200 p-4">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-base font-semibold text-slate-800">
          {series.commodity} — {series.variable.replace(/_/g, " ")}
        </h2>
        <span className="text-xs text-slate-500">
          {series.geography_name} · {series.frequency} · {series.unit}
          {series.frozen ? " · frozen" : " · not frozen"}
        </span>
      </div>

      <div className="h-64 w-full">
        <ResponsiveContainer>
          <LineChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
            <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" />
            <XAxis dataKey="period" tick={{ fontSize: 11 }} minTickGap={28} />
            <YAxis tick={{ fontSize: 11 }} width={52} />
            <Tooltip
              contentStyle={{ fontSize: 12 }}
              labelFormatter={(_, rows) => rows?.[0]?.payload?.periodLabel ?? ""}
              formatter={(v, name) => [v, name === "flagged" ? "flagged value" : series.unit]}
            />
            <Line
              type="monotone"
              dataKey="value"
              stroke="#15803d"
              strokeWidth={1.8}
              dot={false}
              connectNulls={false}
            />
            <Scatter dataKey="flagged" fill="#d9a441" shape="circle" />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {observations.length > 0 && observations.at(-1)?.period && (
        <p className="mt-2 text-xs text-slate-600">
          Latest slot: {observations.at(-1).period.month_label} {observations.at(-1).period.year}
          {" · "}{observations.at(-1).period.quarter_label}{" · "}{observations.at(-1).period.year}
        </p>
      )}

      <dl className="mt-3 grid grid-cols-3 gap-2 text-xs">
        <div className="rounded bg-slate-50 p-2">
          <dt className="text-slate-500">observations</dt>
          <dd className="font-semibold text-slate-800">{quality.n}</dd>
        </div>
        <div className="rounded bg-slate-50 p-2">
          <dt className="text-slate-500">flagged</dt>
          <dd className="font-semibold text-amber-700">
            {quality.n_flagged} / {quality.n}
          </dd>
        </div>
        <div className="rounded bg-slate-50 p-2">
          <dt className="text-slate-500">missing</dt>
          <dd className="font-semibold text-slate-800">
            {quality.n_missing} / {quality.n}
          </dd>
        </div>
      </dl>
      <p className="mt-2 text-[11px] leading-snug text-slate-500">{quality.note}</p>
      <p className="mt-2 border-t border-slate-100 pt-2 text-[11px] leading-snug text-slate-500">
        {attribution.text}
      </p>
    </div>
  );
}
