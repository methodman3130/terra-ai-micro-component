import { useEffect, useState } from "react";
import { Brand, PineRule } from "./Brand";

/**
 * Public methods and data provenance.
 *
 * Deliberately readable without signing in. The underlying statistics are
 * public and CC BY 4.0, and a prototype that claims reproducibility while
 * keeping its own provenance behind a login is claiming it to nobody. The
 * curated series themselves remain gated; what is open here is the account of
 * where they came from, how they were cleaned, and what they can bear.
 */

const BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

const Section = ({ title, children }) => (
  <section className="mb-7">
    <h2 className="mb-2 border-b border-uc-green/20 pb-1 text-sm font-semibold uppercase tracking-wide text-uc-green-dark">
      {title}
    </h2>
    {children}
  </section>
);

const Row = ({ label, children }) => (
  <div className="flex flex-wrap gap-x-3 gap-y-0.5 border-b border-slate-100 py-1.5 text-sm">
    <dt className="w-56 shrink-0 text-slate-500">{label}</dt>
    <dd className="min-w-0 flex-1 text-slate-800">{children}</dd>
  </div>
);

export default function MethodsPage({ onBack }) {
  const [methods, setMethods] = useState(null);
  const [fitness, setFitness] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    Promise.all([
      fetch(`${BASE}/methods`).then((r) => (r.ok ? r.json() : Promise.reject(new Error(r.status)))),
      fetch(`${BASE}/fitness`).then((r) => (r.ok ? r.json() : Promise.reject(new Error(r.status)))),
    ])
      .then(([m, f]) => {
        setMethods(m);
        setFitness(f);
      })
      .catch((e) => setError(String(e.message ?? e)));
  }, []);

  return (
    <div className="min-h-screen bg-uc-mist text-slate-900">
      <PineRule />
      <header className="border-b border-uc-green/15 bg-white">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-3 px-4 py-3">
          <Brand compact />
          <button
            onClick={onBack}
            className="rounded border border-slate-300 px-3 py-1 text-sm hover:bg-uc-mist"
          >
            Back
          </button>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-4 py-6">
        <h1 className="text-lg font-semibold text-uc-green-dark">
          Methods and data provenance
        </h1>
        <p className="mt-1 max-w-3xl text-sm text-slate-600">
          This page is public so that the claims made by the prototype can be checked
          without an account. It describes every source extract behind the curated
          layer, the cleaning rules applied, the evaluation design, and what the record
          does and does not support.
        </p>

        {error && (
          <div className="mt-4 rounded border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">
            Could not load the provenance record ({error}). The underlying statistics
            remain public at the source portal regardless.
          </div>
        )}

        {methods && (
          <div className="mt-6 rounded-lg border border-slate-200 bg-white p-5">
            <Section title="What this is">
              <dl>
                <Row label="Status">{methods.status}</Row>
                <Row label="Issues forecasts">
                  <span className="font-medium text-rose-700">No.</span>{" "}
                  {methods.design.verdict_meaning}
                </Row>
                <Row label="Pre-registered verdict">{methods.design.verdict}</Row>
              </dl>
            </Section>

            <Section title="Geography and frequency">
              <dl>
                <Row label="Published frequency">{methods.design.frequency}</Row>
                <Row label="Published geography">{methods.design.geography_published}</Row>
                <Row label="Rendered on">{methods.design.geography_rendered} polygons</Row>
                <Row label="Observation window">{methods.design.observation_window}</Row>
                <Row label="Scoring cutoff">{methods.design.scoring_cutoff}</Row>
              </dl>
              <p className="mt-2 rounded bg-amber-50 p-2 text-xs text-amber-900">
                {methods.design.geography_warning}
              </p>
            </Section>

            <Section title="Source extracts">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="text-slate-500">
                    <tr>
                      <th className="py-1 pr-3">Table</th>
                      <th className="py-1 pr-3">Title</th>
                      <th className="py-1 pr-3">Retrieved</th>
                      <th className="py-1 pr-3">Vintage</th>
                      <th className="py-1 pr-3">SHA-256 of raw response</th>
                      <th className="py-1">Licence</th>
                    </tr>
                  </thead>
                  <tbody>
                    {methods.extracts.map((e, i) => (
                      <tr key={i} className="border-t border-slate-100 align-top">
                        <td className="py-1 pr-3 font-mono">{e.source_table}</td>
                        <td className="py-1 pr-3">{e.source_table_title}</td>
                        <td className="py-1 pr-3 whitespace-nowrap">
                          {String(e.retrieved_at).slice(0, 10)}
                        </td>
                        <td className="py-1 pr-3">{e.vintage}</td>
                        <td className="py-1 pr-3 break-all font-mono text-[10px]">
                          {e.raw_checksum}
                        </td>
                        <td className="py-1 whitespace-nowrap">{e.permitted_use}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="mt-2 text-xs text-slate-500">{methods.attribution_note}</p>
              <p className="mt-1 text-xs text-amber-800">{methods.vintage_warning}</p>
            </Section>

            <Section title="Cleaning rules">
              <ul className="space-y-2 text-sm">
                {methods.cleaning_rules.map((r) => (
                  <li key={r.rule_id} className="rounded border border-slate-200 p-2">
                    <span className="font-mono text-xs font-semibold">{r.rule_id}</span>{" "}
                    <span className="text-slate-700">{r.trigger}</span>
                    <div className="mt-0.5 text-xs text-slate-600">{r.action}</div>
                    <div className="text-xs text-rose-700">{r.never}</div>
                  </li>
                ))}
              </ul>
              {methods.cleaning_runs?.length > 0 && (
                <p className="mt-2 text-xs text-slate-500">
                  Applied in {methods.cleaning_runs.length} logged runs; rows affected are
                  recorded per rule.
                </p>
              )}
            </Section>

            <Section title="Evaluation design">
              <dl>
                <Row label="Horizons assessed">
                  {methods.design.horizons_assessed.join(", ")} months (primary:{" "}
                  {methods.design.primary_horizon})
                </Row>
                <Row label="Minimum training">
                  {methods.design.minimum_training_observations.general} observations;{" "}
                  {methods.design.minimum_training_observations.AutoARIMA_monthly} for AutoARIMA
                </Row>
                <Row label="Acceptance rule">{methods.design.acceptance_rule}</Row>
              </dl>
            </Section>

            {fitness && (
              <Section title="Data fitness by series">
                <p className="mb-2 text-xs text-slate-600">
                  {fitness.n_series} series; {fitness.n_trainable} have enough usable
                  observations to train under the protocol;{" "}
                  <span className="font-semibold text-rose-700">
                    {fitness.n_forecast_permitted} are permitted a forecast claim.
                  </span>
                </p>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead className="text-slate-500">
                      <tr>
                        <th className="py-1 pr-3">Series</th>
                        <th className="py-1 pr-2 text-right">Slots</th>
                        <th className="py-1 pr-2 text-right">Published</th>
                        <th className="py-1 pr-2 text-right">Flagged zero</th>
                        <th className="py-1 pr-2 text-right">Scoreable</th>
                        <th className="py-1 pr-3">Latest valid</th>
                        <th className="py-1">Forecast permitted</th>
                      </tr>
                    </thead>
                    <tbody>
                      {fitness.series.map((s) => (
                        <tr key={s.series_id} className="border-t border-slate-100 align-top">
                          <td className="py-1 pr-3">{s.commodity}</td>
                          <td className="py-1 pr-2 text-right tabular-nums">{s.slots}</td>
                          <td className="py-1 pr-2 text-right tabular-nums">{s.published}</td>
                          <td className="py-1 pr-2 text-right tabular-nums">{s.flagged_zero}</td>
                          <td className="py-1 pr-2 text-right tabular-nums">{s.scoreable}</td>
                          <td className="py-1 pr-3 whitespace-nowrap">
                            {s.latest_valid_period ?? "—"}
                          </td>
                          <td className="py-1">
                            <span className="font-semibold text-rose-700">No</span>
                            <div className="text-[10px] leading-tight text-slate-500">
                              {s.status_reason}
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="mt-2 text-xs text-slate-600">{fitness.note}</p>
              </Section>
            )}

            <Section title="Reproducibility">
              <p className="text-sm text-slate-700">{methods.reproducibility.note}</p>
              <p className="mt-1 text-sm">
                <a
                  className="text-uc-green-dark underline underline-offset-2"
                  href={methods.reproducibility.repository}
                  target="_blank"
                  rel="noreferrer noopener"
                >
                  Code, derived data, checksums, protocol and benchmark records
                </a>
              </p>
              <p className="mt-1 text-xs text-slate-500">
                Source statistics remain available from{" "}
                <a
                  className="underline underline-offset-2"
                  href={methods.source}
                  target="_blank"
                  rel="noreferrer noopener"
                >
                  the source portal
                </a>{" "}
                under{" "}
                <a
                  className="underline underline-offset-2"
                  href={methods.licence_url}
                  target="_blank"
                  rel="noreferrer noopener"
                >
                  {methods.licence}
                </a>
                .
              </p>
            </Section>
          </div>
        )}

        {!methods && !error && (
          <p className="mt-6 text-sm text-slate-500">Loading provenance record…</p>
        )}
      </main>
    </div>
  );
}
