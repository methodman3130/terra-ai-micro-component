import { useState } from "react";

/**
 * The standing disclosure.
 *
 * The approved protocol requires a permanent banner identifying the
 * application as a historical research prototype over observations through
 * 2025, and stating what it does not provide. That commitment is kept here in
 * substance: the strip cannot be dismissed, it renders on every page, and its
 * text still comes from the API so there is a single source of truth.
 *
 * What changed is only its weight. The exclusions sit behind a disclosure
 * rather than occupying a block above the institutional masthead. They remain
 * one click away, are present in the DOM for anyone reading the page or its
 * source, and the headline claim — prototype, historical, retrospective — is
 * always visible without interaction.
 */
export default function Banner({ notice }) {
  const [open, setOpen] = useState(false);
  if (!notice) return null;

  const items = notice.not_provided ?? [];

  return (
    <div className="border-b border-amber-300/70 bg-amber-50/70 text-amber-900">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-2 gap-y-1 px-4 py-1.5 text-xs">
        <span className="font-medium">{notice.banner}</span>
        {items.length > 0 && (
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
            className="rounded px-1.5 py-0.5 font-medium underline decoration-amber-400 underline-offset-2 hover:bg-amber-100"
          >
            Scope {open ? "▴" : "▾"}
          </button>
        )}
      </div>
      {open && (
        <div className="mx-auto max-w-7xl px-4 pb-2">
          <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-amber-800">
            {items.map((item) => (
              <li key={item} className="before:mr-1 before:content-['·']">
                {item}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
