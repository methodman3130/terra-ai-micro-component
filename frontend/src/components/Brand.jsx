/**
 * University of the Cordilleras wordmark.
 *
 * This is a typographic lockup, not a reproduction of the official seal. Drop
 * the real asset into `public/uc-logo.svg` and it is used automatically — the
 * wordmark is the fallback, so the build never ships an approximated crest.
 */
import { useEffect, useState } from "react";

export function Brand({ compact = false }) {
  const [logo, setLogo] = useState(null);

  useEffect(() => {
    // Probe for an official asset; fall back silently to the wordmark.
    const img = new Image();
    img.onload = () => setLogo("/uc-logo.svg");
    img.onerror = () => setLogo(null);
    img.src = "/uc-logo.svg";
  }, []);

  return (
    <div className="flex items-center gap-3">
      {logo ? (
        <img src={logo} alt="University of the Cordilleras" className="h-10 w-auto" />
      ) : (
        <div
          aria-hidden
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-uc-green text-sm font-bold tracking-tight text-white ring-1 ring-uc-green-dark"
        >
          UC
        </div>
      )}
      <div className="leading-tight">
        <div className={`font-semibold text-uc-green-dark ${compact ? "text-sm" : "text-base"}`}>
          University of the Cordilleras
        </div>
        <div className="text-[11px] text-slate-500">
          Office of the VP for Research, Innovation and Institutional Planning
        </div>
      </div>
    </div>
  );
}

export function PineRule() {
  // A thin ridge motif: Cordillera pine green through to the highland gold.
  return (
    <div className="h-1 w-full bg-gradient-to-r from-uc-green-dark via-uc-green to-uc-gold" />
  );
}
