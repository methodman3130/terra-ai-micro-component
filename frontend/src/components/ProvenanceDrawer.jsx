import { useEffect, useState } from "react";
import { api } from "../lib/api";

/**
 * Every extract behind what is on screen, with checksums.
 *
 * This is the drawer a reviewer opens to ask "where did this number come
 * from". The vintage warning is shown at the top, not buried, because a 2026
 * retrieval of 2015 data is not what an analyst knew in 2015.
 */
export default function ProvenanceDrawer({ open, onClose }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!open) return;
    api.provenance().then(setData).catch((e) => setError(e.message));
  }, [open]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-slate-900/30" onClick={onClose}>
      <aside
        className="h-full w-full max-w-xl overflow-y-auto bg-white p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-start justify-between">
          <h2 className="text-lg font-semibold text-slate-800">Provenance</h2>
          <button
            onClick={onClose}
            className="rounded px-2 py-1 text-sm text-slate-500 hover:bg-slate-100"
          >
            close
          </button>
        </div>

        {error && <p className="text-sm text-rose-600">{error}</p>}

        {data && (
          <>
            <div className="mb-4 rounded border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
              {data.vintage_warning}
            </div>
            <p className="mb-4 text-xs text-slate-600">
              Licence: {data.licence} ·{" "}
              <a className="underline" href={data.licence_url} target="_blank" rel="noreferrer">
                terms
              </a>{" "}
              ·{" "}
              <a className="underline" href={data.source} target="_blank" rel="noreferrer">
                source portal
              </a>
            </p>

            <ul className="space-y-3">
              {data.extracts.map((e) => (
                <li key={e.extract_id} className="rounded border border-slate-200 p-3 text-xs">
                  <div className="font-medium text-slate-800">
                    {e.source_table} — {e.source_table_title}
                  </div>
                  <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-slate-600">
                    <dt className="text-slate-400">retrieved</dt>
                    <dd>{e.retrieved_at}</dd>
                    <dt className="text-slate-400">reference period</dt>
                    <dd>{e.reference_period}</dd>
                    <dt className="text-slate-400">release date</dt>
                    <dd>{e.release_date ?? "not published by PSA"}</dd>
                    <dt className="text-slate-400">vintage</dt>
                    <dd>{e.vintage}</dd>
                    <dt className="text-slate-400">permitted use</dt>
                    <dd>{e.permitted_use}</dd>
                  </dl>
                  <div className="mt-2 break-all font-mono text-[10px] text-slate-500">
                    sha256 {e.raw_checksum}
                  </div>
                </li>
              ))}
            </ul>

            {data.count === 0 && (
              <p className="text-sm text-slate-500">
                No extracts loaded yet. Run the retrieval job on the host that can reach
                openstat.psa.gov.ph.
              </p>
            )}
          </>
        )}
      </aside>
    </div>
  );
}
