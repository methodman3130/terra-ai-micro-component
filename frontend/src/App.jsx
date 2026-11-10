import { useEffect, useState } from "react";
import Banner from "./components/Banner";
import MapPanel from "./components/MapPanel";
import SeriesPanel from "./components/SeriesPanel";
import BenchmarkPanel from "./components/BenchmarkPanel";
import ProvenanceDrawer from "./components/ProvenanceDrawer";
import { api } from "./lib/api";
import { AuthProvider, useAuth } from "./lib/auth";
import AuthScreen from "./components/AuthScreen";
import AdminPanel from "./components/AdminPanel";
import { Brand, PineRule } from "./components/Brand";
import MethodsPage from "./components/MethodsPage";

const BENGUET = "1401100000"; // PSGC: province digits are positions 3-5
// Commodities are whatever the register actually holds. Hard-coding them meant
// Potato was loaded but unreachable from the UI, and every new crop needed a
// frontend release to become visible.
const FALLBACK_COMMODITIES = ["Cabbage", "Carrot", "Potato"];
const VARIABLES = [
  { key: "farmgate_price", label: "Farmgate price" },
  { key: "production", label: "Production" },
  { key: "area_harvested", label: "Area harvested" },
];

export default function App() {
  return (
    <AuthProvider>
      <Gate />
    </AuthProvider>
  );
}

/** Nothing but the sign-in screen renders until the session is resolved. */
function Gate() {
  const { user, ready } = useAuth();
  const [methods, setMethods] = useState(false);
  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-uc-mist text-sm text-slate-500">
        Loading session…
      </div>
    );
  }
  // The methods page is reachable without an account. The curated series are not.
  if (methods) return <MethodsPage onBack={() => setMethods(false)} />;
  return user ? (
    <Panel onMethods={() => setMethods(true)} />
  ) : (
    <AuthScreen onMethods={() => setMethods(true)} />
  );
}

function Panel({ onMethods }) {
  const { user, isAdmin, signOut } = useAuth();
  const [adminOpen, setAdminOpen] = useState(false);
  const [notice, setNotice] = useState(null);
  const [health, setHealth] = useState(null);
  const [commodities, setCommodities] = useState(FALLBACK_COMMODITIES);
  const [commodity, setCommodity] = useState(FALLBACK_COMMODITIES[0]);
  const [variable, setVariable] = useState("farmgate_price");
  const [geo, setGeo] = useState(null);
  const [selected, setSelected] = useState(null);
  const [selectedSeries, setSelectedSeries] = useState(null);
  const [observations, setObservations] = useState(null);
  const [benchmark, setBenchmark] = useState(null);
  const [benchmarkError, setBenchmarkError] = useState(null);
  const [drawer, setDrawer] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.notice().then(setNotice).catch(() => {});
    api.health().then(setHealth).catch(() => setHealth({ database: "unavailable" }));
    // Populate the picker from the series register rather than a constant, so
    // loading a new crop makes it selectable without a frontend release. The
    // fallback only covers the case where /series is unreachable.
    api
      .series()
      .then((r) => {
        const names = [...new Set((r.series ?? []).map((s) => s.commodity))].sort();
        if (names.length) {
          setCommodities(names);
          setCommodity((c) => (names.includes(c) ? c : names[0]));
        }
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    setError(null);
    api
      .municipalities({ province_code: BENGUET, commodity, variable })
      .then(setGeo)
      .catch((e) => setError(e.message));
  }, [commodity, variable]);

  // The geo response carries the series_id that shades each polygon, so a
  // click resolves directly instead of re-deriving it from a geography code —
  // which would be wrong here anyway, since these prices are provincial.
  useEffect(() => {
    if (!selectedSeries) return;
    setObservations(null);
    setBenchmark(null);
    setBenchmarkError(null);
    api
      .observations(selectedSeries)
      .then(setObservations)
      .catch((e) => setError(e.message));
    api.benchmark(selectedSeries).then(setBenchmark).catch(setBenchmarkError);
  }, [selectedSeries]);

  // Auto-select the shaded series so the panels are populated on first load.
  useEffect(() => {
    const sid = geo?.features?.find((f) => f.properties.series_id)?.properties?.series_id;
    if (sid) setSelectedSeries(sid);
  }, [geo]);

  const unit = geo?.features?.find((f) => f.properties.unit)?.properties?.unit;

  return (
    <div className="min-h-screen bg-uc-mist text-slate-900">
      <PineRule />
      <Banner notice={notice} />

      <header className="border-b border-uc-green/15 bg-white">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-4 py-3">
          <div className="flex items-center gap-4">
            <Brand compact />
            <div className="hidden border-l border-slate-200 pl-4 sm:block">
              <h1 className="text-base font-semibold text-uc-green-dark">
                Project TERRA-AI
              </h1>
              <p className="text-xs text-slate-500">Benguet farmgate baseline</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <select
              value={commodity}
              onChange={(e) => setCommodity(e.target.value)}
              className="rounded border border-slate-300 px-2 py-1 text-sm focus:border-uc-green focus:outline-none"
            >
              {commodities.map((c) => (
                <option key={c}>{c}</option>
              ))}
            </select>
            <select
              value={variable}
              onChange={(e) => setVariable(e.target.value)}
              className="rounded border border-slate-300 px-2 py-1 text-sm focus:border-uc-green focus:outline-none"
            >
              {VARIABLES.map((v) => (
                <option key={v.key} value={v.key}>
                  {v.label}
                </option>
              ))}
            </select>
            <button
              onClick={() => setDrawer(true)}
              className="rounded border border-slate-300 px-3 py-1 text-sm hover:bg-uc-mist"
            >
              Provenance
            </button>
            <button
              onClick={onMethods}
              className="rounded border border-slate-300 px-3 py-1 text-sm hover:bg-uc-mist"
            >
              Methods &amp; fitness
            </button>
            {isAdmin && (
              <button
                onClick={() => setAdminOpen(true)}
                className="rounded border border-uc-green/40 bg-uc-green/5 px-3 py-1 text-sm font-medium text-uc-green-dark hover:bg-uc-green/10"
              >
                Users
              </button>
            )}
            <div className="ml-1 flex items-center gap-2 border-l border-slate-200 pl-3">
              <span className="text-xs text-slate-600">
                {user.display_name}
                <span className="ml-1 rounded bg-uc-green/10 px-1.5 py-0.5 text-[10px] font-medium text-uc-green-dark">
                  {user.role}
                </span>
              </span>
              <button
                onClick={signOut}
                className="rounded px-2 py-1 text-sm text-slate-600 hover:bg-slate-100"
              >
                Sign out
              </button>
            </div>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl space-y-4 px-4 py-5">
        {health?.database === "unavailable" && (
          <div className="rounded border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">
            Database unavailable. The interface is running but no curated data is loaded —
            apply <code className="font-mono">db/001_schema.sql</code> and run the retrieval
            job on a host that can reach openstat.psa.gov.ph.
          </div>
        )}
        {error && (
          <div className="rounded border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
            {error}
          </div>
        )}

        <MapPanel
          featureCollection={geo}
          unit={unit}
          selectedCode={selected}
          onSelect={(code) => {
            setSelected(code);
            const f = geo?.features?.find((x) => x.properties.psgc_code === code);
            if (f?.properties?.series_id) setSelectedSeries(f.properties.series_id);
          }}
        />

        {geo?.metadata && (
          <p className="text-[11px] text-slate-500">
            {geo.metadata.grain_warning} Boundary source: {geo.metadata.boundary_source}; PSGC vintage{" "}
            {geo.metadata.psgc_vintage ?? "unknown"}. Municipalities without an observation:{" "}
            {geo.metadata.n_without_data}.
          </p>
        )}

        <p className="rounded border border-amber-300/70 bg-amber-50/70 px-3 py-2 text-xs text-amber-900">
          <strong>Monthly, province-level published statistics.</strong> Not municipal or
          farm observations, not real-time, and not decision advice. Panels below show
          retrospective back-test scores only; no forecast is issued for any series.
        </p>

        <div className="grid gap-4 lg:grid-cols-2">
          <SeriesPanel payload={observations} />
          <BenchmarkPanel payload={benchmark} error={benchmarkError} />
        </div>
      </main>

      <ProvenanceDrawer open={drawer} onClose={() => setDrawer(false)} />
      <AdminPanel open={adminOpen} onClose={() => setAdminOpen(false)} />

      <footer className="border-t border-uc-green/15 bg-white">
        <div className="mx-auto max-w-7xl px-4 py-3 text-[11px] text-slate-500">
          Data: Philippine Statistics Authority OpenSTAT, licensed CC BY 4.0, modified by the
          University of the Cordilleras. PSA does not endorse this use. Boundaries: PSGC
          shapefiles (MIT). Research prototype — not an advisory service.
        </div>
      </footer>
    </div>
  );
}
