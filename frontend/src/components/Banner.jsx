/**
 * The standing disclosure. The proposal requires a permanent banner; this one
 * is permanent in the strict sense — it has no dismiss control, and its text
 * comes from the API so there is a single source of truth.
 */
export default function Banner({ notice }) {
  if (!notice) return null;
  return (
    <div className="bg-amber-50 border-b border-amber-300 text-amber-900">
      <div className="mx-auto max-w-7xl px-4 py-2 text-sm">
        <span className="font-semibold">{notice.banner}</span>
        <ul className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-amber-800">
          {(notice.not_provided ?? []).map((item) => (
            <li key={item} className="before:mr-1 before:content-['·']">
              {item}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
