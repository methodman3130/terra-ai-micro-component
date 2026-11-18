import { useEffect, useMemo, useState } from "react";
import {
  Area, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis,
  Bar, BarChart, ReferenceLine, Cell,
} from "recharts";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { buildForecast, monotoneCubic } from "../lib/forecast";
import { cropMeta } from "../lib/crops";

/**
 * Farmer view.
 *
 * Deliberately a different product from the research panels: it answers when to
 * harvest, roughly how much, and what the month is likely to pay. That means it
 * issues forecasts, which the research view refuses to do. The honesty budget is
 * spent differently here — every predicted figure is shown with its back-tested
 * range, the daily curve is labelled as interpolated wherever it appears, and
 * the About tab states plainly where the model loses to "same as last month".
 */

const MONTHS = {
  en: ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"],
  fil: ["Ene","Peb","Mar","Abr","May","Hun","Hul","Ago","Set","Okt","Nob","Dis"],
};
const MONTHS_LONG = {
  en: ["January","February","March","April","May","June","July","August","September","October","November","December"],
  fil: ["Enero","Pebrero","Marso","Abril","Mayo","Hunyo","Hulyo","Agosto","Setyembre","Oktubre","Nobyembre","Disyembre"],
};

const DAY = 86400000;
const peso = (n) =>
  n === null || n === undefined || !Number.isFinite(n)
    ? "—"
    : "₱" + (n >= 1000 ? Math.round(n).toLocaleString("en-PH")
        : n.toLocaleString("en-PH", { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
const kgs = (n) =>
  n >= 1000 ? (n / 1000).toLocaleString("en-PH", { maximumFractionDigits: 1 }) + " t"
            : Math.round(n).toLocaleString("en-PH") + " kg";

export default function FarmerView({ onExit }) {
  const { user, signOut } = useAuth();
  const [lang, setLang] = useState(() => localStorage.getItem("terra.lang") || "en");
  const [tab, setTab] = useState("harvest");

  const [series, setSeries] = useState([]);
  const [commodity, setCommodity] = useState("");
  const [obs, setObs] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [planted, setPlanted] = useState(() =>
    new Date(Date.now() - 40 * DAY).toISOString().slice(0, 10));
  const [area, setArea] = useState(2000);
  const [unitMul, setUnitMul] = useState(1);
  const [gran, setGran] = useState("m");

  const t = (en, fil) => (lang === "en" ? en : fil);
  useEffect(() => { localStorage.setItem("terra.lang", lang); }, [lang]);

  // Farmgate price only: production and area-harvested series answer a
  // different question and would silently feed the wrong units into the model.
  useEffect(() => {
    api.series({ variable: "farmgate_price" })
      .then((r) => {
        const rows = (r.series ?? []).filter(
          (s) => !s.variable || s.variable === "farmgate_price");
        const withMeta = rows.filter((s) => cropMeta(s.commodity));
        const use = withMeta.length ? withMeta : rows;
        setSeries(use);
        setCommodity((c) => (use.some((s) => s.commodity === c) ? c : use[0]?.commodity ?? ""));
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const activeSeries = useMemo(
    () => series.find((s) => s.commodity === commodity) ?? null, [series, commodity]);

  useEffect(() => {
    const id = activeSeries?.series_id ?? activeSeries?.id;
    if (!id) return;
    setObs(null);
    setError(null);
    api.observations(id).then(setObs).catch((e) => setError(e.message));
  }, [activeSeries]);

  const F = useMemo(() => (obs ? buildForecast(obs.observations ?? []) : null), [obs]);
  const meta = cropMeta(commodity);

  return (
    <div className="min-h-screen bg-uc-mist pb-24 text-slate-900">
      <header className="sticky top-0 z-20 bg-uc-green-dark text-white">
        <div className="mx-auto flex max-w-3xl items-center gap-3 px-4 py-3">
          <div className="min-w-0 flex-1">
            <h1 className="truncate text-lg font-bold leading-tight">TERRA Ani</h1>
            <p className="truncate text-[11px] uppercase tracking-wide text-white/75">
              {t("Benguet · farmgate outlook", "Benguet · presyo sa bukid")}
            </p>
          </div>
          <button
            onClick={() => setLang(lang === "en" ? "fil" : "en")}
            className="rounded-full border border-white/30 bg-white/10 px-3 py-1.5 text-xs font-semibold"
          >
            {lang === "en" ? "FIL" : "ENG"}
          </button>
          <button
            onClick={onExit}
            className="rounded-full border border-white/30 px-3 py-1.5 text-xs font-semibold"
            title={t("Switch to the research view", "Lumipat sa research view")}
          >
            {t("Research", "Research")}
          </button>
        </div>
      </header>

      <main className="mx-auto max-w-3xl space-y-4 px-4 py-4">
        {error && (
          <div className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">{error}</div>
        )}
        {loading && <p className="text-sm text-slate-500">{t("Loading series…", "Naglo-load…")}</p>}

        {!loading && !F && !error && (
          <div className="rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-600">
            {t("This series is too short to back-test, so no forecast is shown. That is an honest empty state, not a failure.",
               "Masyadong maikli ang serye para masubok, kaya walang hula. Tapat na walang laman, hindi palya.")}
          </div>
        )}

        {F && (
          <>
            {tab === "harvest" && (
              <HarvestTab {...{ F, meta, commodity, series, setCommodity, planted, setPlanted,
                area, setArea, unitMul, setUnitMul, lang, t }} />
            )}
            {tab === "price" && (
              <PriceTab {...{ F, commodity, series, setCommodity, gran, setGran, lang, t,
                lastPublished: obs?.series }} />
            )}
            {tab === "season" && (
              <SeasonTab {...{ F, meta, commodity, series, setCommodity, lang, t }} />
            )}
            {tab === "about" && <AboutTab {...{ F, obs, meta, commodity, lang, t, user, signOut }} />}
          </>
        )}
      </main>

      <nav className="fixed inset-x-0 bottom-0 z-20 border-t border-slate-200 bg-white">
        <div className="mx-auto flex max-w-3xl">
          {[
            ["harvest", t("Harvest", "Ani")],
            ["price", t("Price", "Presyo")],
            ["season", t("Season", "Panahon")],
            ["about", t("About", "Tungkol")],
          ].map(([k, label]) => (
            <button
              key={k}
              onClick={() => { setTab(k); window.scrollTo(0, 0); }}
              aria-selected={tab === k}
              className={`flex-1 border-t-[3px] px-2 py-3 text-xs font-semibold ${
                tab === k ? "border-uc-green text-uc-green-dark" : "border-transparent text-slate-500"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </nav>
    </div>
  );
}

/* ------------------------------------------------------------------ */

function CropPicker({ commodity, series, setCommodity, t }) {
  return (
    <div>
      <label className="mb-1 block text-xs font-semibold text-slate-500">{t("Crop", "Pananim")}</label>
      <select
        value={commodity}
        onChange={(e) => setCommodity(e.target.value)}
        className="w-full rounded-lg border border-slate-300 bg-white px-3 py-3 text-base"
      >
        {series.map((s) => (
          <option key={s.series_id ?? s.id ?? s.commodity} value={s.commodity}>{s.commodity}</option>
        ))}
      </select>
    </div>
  );
}

const Card = ({ children, className = "" }) => (
  <div className={`rounded-lg border border-slate-200 bg-white p-4 ${className}`}>{children}</div>
);
const Eyebrow = ({ children }) => (
  <p className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">{children}</p>
);

function priceAt(F, y, m) {
  const h = F.hist.find((o) => o.y === y && o.m === m);
  if (h) return { p: h.v, lo: h.v, hi: h.v, kind: "actual" };
  const f = F.fc.find((o) => o.y === y && o.m === m);
  if (f) return { ...f, kind: "fc" };
  return null;
}

/* ------------------------------ harvest --------------------------- */

function HarvestTab({ F, meta, commodity, series, setCommodity, planted, setPlanted,
  area, setArea, unitMul, setUnitMul, lang, t }) {
  const d0 = planted ? new Date(planted + "T00:00:00Z") : null;
  const dtm = meta?.dtm ?? [75, 100];
  const a = d0 ? new Date(d0.getTime() + dtm[0] * DAY) : null;
  const b = d0 ? new Date(d0.getTime() + dtm[1] * DAY) : null;
  const fd = (x) => `${x.getUTCDate()} ${MONTHS[lang][x.getUTCMonth()]} ${x.getUTCFullYear()}`;

  const areaHa = (Number(area) || 0) * unitMul / 10000;
  const vol = meta ? areaHa * meta.yieldKgHa : null;

  const mid = a && b ? new Date((a.getTime() + b.getTime()) / 2) : null;
  const Y = mid?.getUTCFullYear();
  const M = mid ? mid.getUTCMonth() + 1 : null;
  const pr = mid ? priceAt(F, Y, M) : null;
  const si = M ? F.seasonal[M] : null;

  // Only months the crop could actually be harvested in: suggesting a price
  // peak that falls before maturity is advice to harvest an immature field.
  const opts = [];
  if (mid && a) {
    const earliest = Date.UTC(a.getUTCFullYear(), a.getUTCMonth(), 1);
    for (let k = -2; k <= 4; k += 1) {
      const dt = new Date(Date.UTC(Y, M - 1 + k, 15));
      if (dt.getTime() < earliest) continue;
      const p = priceAt(F, dt.getUTCFullYear(), dt.getUTCMonth() + 1);
      if (p) opts.push({ k, y: dt.getUTCFullYear(), m: dt.getUTCMonth() + 1, ...p });
    }
  }
  const base = opts.find((o) => o.k === 0);
  const best = [...opts].sort((x, y2) => y2.p - x.p)[0];

  const today = Date.now();
  const elapsed = d0 ? Math.max(0, Math.min(dtm[1], (today - d0.getTime()) / DAY)) : 0;
  const daysLeft = a ? Math.round((a.getTime() - today) / DAY) : null;

  return (
    <div className="space-y-4">
      <Card className="bg-gradient-to-b from-uc-green-light/30 to-white">
        <Eyebrow>{t("Plan your harvest", "Planuhin ang ani")}</Eyebrow>
        <div className="grid gap-3 sm:grid-cols-2">
          <CropPicker {...{ commodity, series, setCommodity, t }} />
          <div>
            <label className="mb-1 block text-xs font-semibold text-slate-500">
              {t("Date planted / transplanted", "Petsa ng tanim / lipat-tanim")}
            </label>
            <input type="date" value={planted} onChange={(e) => setPlanted(e.target.value)}
              className="w-full rounded-lg border border-slate-300 bg-white px-3 py-3 text-base" />
          </div>
          <div>
            <label className="mb-1 block text-xs font-semibold text-slate-500">
              {t("Area planted", "Laki ng taniman")}
            </label>
            <input type="number" min="0" step="any" value={area}
              onChange={(e) => setArea(e.target.value)}
              className="w-full rounded-lg border border-slate-300 bg-white px-3 py-3 text-base" />
          </div>
          <div>
            <label className="mb-1 block text-xs font-semibold text-slate-500">{t("Unit", "Sukat")}</label>
            <select value={unitMul} onChange={(e) => setUnitMul(Number(e.target.value))}
              className="w-full rounded-lg border border-slate-300 bg-white px-3 py-3 text-base">
              <option value={1}>m² ({t("square meters", "metro kuwadrado")})</option>
              <option value={10000}>ha ({t("hectares", "ektarya")})</option>
            </select>
          </div>
        </div>
      </Card>

      <Card>
        <Eyebrow>{t("Harvest window", "Panahon ng ani")}</Eyebrow>
        <p className="text-2xl font-extrabold leading-tight tracking-tight text-uc-green-dark">
          {a && b ? `${fd(a)} – ${fd(b)}` : "—"}
        </p>
        <p className="mt-1 text-xs text-slate-500">
          {dtm[0]}–{dtm[1]} {t("days from planting", "araw mula sa tanim")}
          {meta?.dtmIndicative && ` · ${t("indicative", "tantiya")}`}
          {meta ? ` · ${meta.dtmBasis}` : ""}
        </p>
        <div className="mt-3 h-2 overflow-hidden rounded bg-slate-200">
          <div className="h-full bg-uc-green" style={{ width: `${(elapsed / dtm[1]) * 100}%` }} />
        </div>
        <p className="mt-1.5 text-xs text-slate-500">
          {daysLeft > 0
            ? `${daysLeft} ${t("days until the earliest harvest date.", "araw bago ang pinakamaagang ani.")}`
            : t("Harvest window is open or past.", "Bukas na o lampas na ang panahon ng ani.")}
        </p>
      </Card>

      <div className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-slate-200 bg-slate-200">
        <Kpi label={t("Expected volume", "Inaasahang dami")}
          value={vol !== null ? kgs(vol) : "—"}
          sub={meta ? `${meta.yieldKgHa / 1000} t/ha × ${areaHa.toFixed(3)} ha` : t("no yield figure", "walang datos")} />
        <Kpi label={t("Predicted price", "Hulang presyo")}
          value={pr ? `${peso(pr.p)}/kg` : "—"}
          sub={pr ? (pr.kind === "actual" ? t("published", "nalathala")
            : `${peso(pr.lo)}–${peso(pr.hi)} · ${MONTHS[lang][M - 1]} ${Y}`) : ""} />
        <Kpi label={t("Gross at farmgate", "Kita sa bukid")}
          value={vol !== null && pr ? peso(vol * pr.p) : "—"}
          sub={vol !== null && pr && pr.kind === "fc" ? `${peso(vol * pr.lo)} – ${peso(vol * pr.hi)}` : ""} />
        <Kpi label={t("Vs. usual for month", "Kumpara sa karaniwan")}
          value={si ? `${si >= 1 ? "+" : ""}${Math.round((si - 1) * 100)}%` : "—"}
          tone={si ? (si > 1.08 ? "good" : si < 0.92 ? "bad" : "flat") : "flat"}
          sub={si ? t(`${MONTHS_LONG.en[M - 1]} is usually ${si >= 1 ? "above" : "below"} the year's average`,
            `Karaniwang ${si >= 1 ? "mas mataas" : "mas mababa"} ang ${MONTHS_LONG.fil[M - 1]}`) : ""} />
      </div>

      {base && best && (
        <Card>
          <Eyebrow>{t("Timing check", "Pagsusuri ng timing")}</Eyebrow>
          {best.k === 0 ? (
            <>
              <Pill tone="good">{t("Your window is the best of the nearby months",
                "Pinakamainam na ang panahon ninyo")}</Pill>
              <p className="mt-2 text-xs leading-relaxed text-slate-600">
                {t("Nothing in the months you could still harvest in is predicted higher.",
                   "Walang mas mataas sa mga buwang maaari pa kayong umani.")}
              </p>
            </>
          ) : (
            <>
              <Pill tone={best.p / base.p - 1 >= 0.15 ? "warn" : "good"}>
                {MONTHS_LONG[lang][best.m - 1]} {best.y}{" "}
                {t("is predicted", "ang hula")} {Math.round((best.p / base.p - 1) * 100)}%
              </Pill>
              <p className="mt-2 text-xs leading-relaxed text-slate-600">
                {t(
                  `Predicted ${peso(best.p)}/kg against ${peso(base.p)}/kg in your window. Holding or staggering the harvest would be worth about ${peso(Math.abs((vol ?? 0) * (best.p - base.p)))} on this volume — before storage loss, extra inputs, and the risk that the prediction is wrong.`,
                  `Hula: ${peso(best.p)}/kg kumpara sa ${peso(base.p)}/kg sa inyong panahon. Ang pagpapaliban o paghahati ng ani ay mga ${peso(Math.abs((vol ?? 0) * (best.p - base.p)))} sa dami ninyo — bago ang sira sa imbakan, dagdag gastos, at panganib na mali ang hula.`
                )}
              </p>
            </>
          )}
        </Card>
      )}

      <Card>
        <h2 className="mb-3 text-sm font-semibold text-slate-800">
          {t("Month by month around your harvest", "Buwan-buwan sa paligid ng ani")}
        </h2>
        <div className="overflow-x-auto">
          <table className="w-full text-right text-[13px] tabular-nums">
            <thead>
              <tr className="text-[10px] uppercase tracking-wider text-slate-500">
                <th className="py-2 pr-2 text-left">{t("Month", "Buwan")}</th>
                <th className="py-2 pl-2">{t("Predicted", "Hula")}</th>
                <th className="py-2 pl-3">{t("Low–high", "Mababa–mataas")}</th>
                <th className="py-2 pl-3">{t("Gross", "Kita")}</th>
              </tr>
            </thead>
            <tbody>
              {opts.map((o) => (
                <tr key={`${o.y}-${o.m}`}
                  className={`border-t border-slate-100 ${o.k === 0 ? "bg-uc-green/5 font-semibold" : ""}`}>
                  <td className="whitespace-nowrap py-2 pr-2 text-left">{MONTHS[lang][o.m - 1]} {o.y}{o.k === 0 ? " ◆" : ""}</td>
                  <td className="whitespace-nowrap py-2 pl-2">{peso(o.p)}</td>
                  <td className="whitespace-nowrap py-2 pl-3 text-slate-500">{o.kind === "fc" ? `${peso(o.lo)}–${peso(o.hi)}` : "—"}</td>
                  <td className="whitespace-nowrap py-2 pl-3">{vol !== null ? peso(vol * o.p) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-[11px] leading-relaxed text-slate-500">
          {t("Low–high is the middle 80% of how wrong this model has been before, at the same number of months ahead.",
             "Ang mababa–mataas ay ang gitnang 80% ng dating pagkakamali ng modelo sa ganito ring layo ng buwan.")}
        </p>
      </Card>
    </div>
  );
}

function Kpi({ label, value, sub, tone = "flat" }) {
  const color = tone === "good" ? "text-uc-green" : tone === "bad" ? "text-rose-700" : "text-slate-900";
  return (
    <div className="bg-white p-3">
      <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">{label}</div>
      <div className={`text-xl font-extrabold tabular-nums ${color}`}>{value}</div>
      {sub ? <div className="mt-0.5 text-[11px] leading-snug text-slate-500">{sub}</div> : null}
    </div>
  );
}
function Pill({ tone = "good", children }) {
  const cls = {
    good: "bg-uc-green/10 text-uc-green-dark",
    warn: "bg-amber-100 text-amber-900",
    bad: "bg-rose-100 text-rose-800",
  }[tone];
  return <span className={`inline-block rounded-full px-3 py-1 text-xs font-bold ${cls}`}>{children}</span>;
}

/* ------------------------------- price ---------------------------- */

function PriceTab({ F, commodity, series, setCommodity, gran, setGran, lang, t }) {
  const now = new Date();
  const cur = priceAt(F, now.getFullYear(), now.getMonth() + 1);
  const nowKey = now.getFullYear() * 12 + now.getMonth();
  const upcoming = F.fc.filter((f) => f.y * 12 + (f.m - 1) >= nowKey).slice(0, 12);

  const data = useMemo(() => {
    const hist = F.hist.slice(-36).map((h) => ({
      x: Date.UTC(h.y, h.m - 1, 15), actual: h.v,
    }));
    const lastH = F.hist[F.hist.length - 1];
    const fc = F.fc.slice(0, 12).map((f) => ({
      x: Date.UTC(f.y, f.m - 1, 15), pred: f.p, band: [f.lo, f.hi],
    }));
    const joined = [
      ...hist,
      ...fc,
    ];
    // Join the two lines at the last published point so there is no visual gap.
    const li = joined.findIndex((d) => d.x === Date.UTC(lastH.y, lastH.m - 1, 15));
    if (li >= 0) { joined[li].pred = lastH.v; joined[li].band = [lastH.v, lastH.v]; }
    if (gran !== "d") return joined;

    // Everything below is in whole days since epoch; mixing that with the
    // millisecond axis is how this silently drew nothing the first time.
    const splitDay = Date.UTC(lastH.y, lastH.m - 1, 15) / DAY;
    const histPts = hist.map((d) => ({ x: d.x / DAY, y: d.actual }));
    const fcPts = [{ x: splitDay, y: lastH.v }, ...fc.map((d) => ({ x: d.x / DAY, y: d.pred }))];
    if (histPts.length < 2 || fcPts.length < 2) return joined;
    const f1 = monotoneCubic(histPts);
    const f2 = monotoneCubic(fcPts);
    const out = [];
    const start = histPts[0].x;
    const end = fcPts[fcPts.length - 1].x;
    for (let x = start; x <= end; x += 3) {
      out.push({
        x: x * DAY,
        actual: x <= splitDay ? f1(x) : null,
        pred: x >= splitDay ? f2(x) : null,
      });
    }
    return out;
  }, [F, gran]);

  const tickFmt = (x) => {
    const d = new Date(x);
    return `${MONTHS.en[d.getUTCMonth()]} ’${String(d.getUTCFullYear()).slice(2)}`;
  };

  return (
    <div className="space-y-4">
      <Card>
        <div className="mb-3"><CropPicker {...{ commodity, series, setCommodity, t }} /></div>
        <div className="mb-4 flex gap-1 rounded-lg bg-slate-100 p-1">
          {[["m", t("Per month", "Kada buwan")], ["d", t("Per day", "Kada araw")]].map(([k, l]) => (
            <button key={k} onClick={() => setGran(k)}
              className={`flex-1 rounded-md px-3 py-2 text-sm font-semibold ${
                gran === k ? "bg-white text-slate-900 shadow-sm" : "text-slate-500"}`}>{l}</button>
          ))}
        </div>

        <p className="text-3xl font-extrabold tracking-tight text-uc-green-dark">
          {cur ? `${peso(cur.p)}/kg` : "—"}
        </p>
        <p className="mt-1 text-xs leading-relaxed text-slate-500">
          {cur && (cur.kind === "actual"
            ? `${MONTHS_LONG[lang][now.getMonth()]} ${now.getFullYear()} · ${t("published by PSA", "nalathala ng PSA")}`
            : `${MONTHS_LONG[lang][now.getMonth()]} ${now.getFullYear()} · ${t("predicted", "hula")} (${peso(cur.lo)}–${peso(cur.hi)}) · ${t("last published", "huling nalathala")}: ${MONTHS[lang][F.lastObs.m - 1]} ${F.lastObs.y} ${peso(F.lastObs.v)}`)}
        </p>

        <div className="mt-3 h-56 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={data} margin={{ top: 8, right: 14, bottom: 4, left: -8 }}>
              <CartesianGrid stroke="#e2e8f0" vertical={false} />
              <XAxis dataKey="x" type="number" scale="time" domain={["dataMin", "dataMax"]}
                tickFormatter={tickFmt} tick={{ fontSize: 10, fill: "#64748b" }} minTickGap={40} />
              <YAxis tick={{ fontSize: 10, fill: "#64748b" }} width={44}
                tickFormatter={(v) => `₱${Math.round(v)}`} />
              <Tooltip
                labelFormatter={(x) => new Date(x).toISOString().slice(0, 10)}
                formatter={(v, n) => [peso(Number(v)), n === "actual" ? t("published", "nalathala") : t("predicted", "hula")]}
                contentStyle={{ fontSize: 12 }} />
              {gran === "m" && (
                <Area dataKey="band" stroke="none" fill="#86efac" fillOpacity={0.55} isAnimationActive={false} />
              )}
              <Line dataKey="actual" stroke="#475569" dot={false} strokeWidth={2} isAnimationActive={false} connectNulls={gran === "m"} />
              <Line dataKey="pred" stroke="#15803d" dot={false} strokeWidth={2} strokeDasharray="5 4" isAnimationActive={false} connectNulls={gran === "m"} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>

        {gran === "d" && (
          <div className="mt-3 rounded-lg border border-amber-300/70 bg-amber-50 p-3 text-xs leading-relaxed text-amber-900">
            {t("The PSA publishes no daily price. This line is drawn between monthly points to show the shape of the month. Any single day's number here is made up — use the month, not the day.",
               "Walang araw-araw na presyo ang PSA. Ang linyang ito ay iginuhit lang sa pagitan ng buwanang punto. Gawa-gawa ang numero ng iisang araw — gamitin ang buwan, hindi ang araw.")}
          </div>
        )}
      </Card>

      <Card>
        <h2 className="mb-3 text-sm font-semibold text-slate-800">{t("Next 12 months", "Susunod na 12 buwan")}</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-right text-[13px] tabular-nums">
            <thead>
              <tr className="text-[10px] uppercase tracking-wider text-slate-500">
                <th className="py-2 pr-2 text-left">{t("Month", "Buwan")}</th>
                <th className="py-2 pl-2">{t("Predicted", "Hula")}</th>
                <th className="py-2 pl-3">{t("Likely", "Malamang")}</th>
                <th className="hidden py-2 pl-3 sm:table-cell">{t("Range", "Saklaw")}</th>
              </tr>
            </thead>
            <tbody>
              {upcoming.map((f) => (
                <tr key={`${f.y}-${f.m}`} className="border-t border-slate-100">
                  <td className="whitespace-nowrap py-2 pr-2 text-left">{MONTHS[lang][f.m - 1]} {f.y}</td>
                  <td className="whitespace-nowrap py-2 pl-2 font-semibold">{peso(f.p)}</td>
                  <td className="whitespace-nowrap py-2 pl-3">{peso(f.lo50)}–{peso(f.hi50)}</td>
                  <td className="hidden whitespace-nowrap py-2 pl-3 text-slate-400 sm:table-cell">{peso(f.lo)}–{peso(f.hi)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

/* ------------------------------ season ---------------------------- */

function SeasonTab({ F, meta, commodity, series, setCommodity, lang, t }) {
  const vals = Object.keys(F.seasonal).map((k) => ({
    m: Number(k), v: F.seasonal[k], pct: Math.round((F.seasonal[k] - 1) * 100),
    label: MONTHS[lang][Number(k) - 1],
  }));
  const best = [...vals].sort((a, b) => b.v - a.v)[0];
  const worst = [...vals].sort((a, b) => a.v - b.v)[0];
  const top = [...vals].sort((a, b) => b.v - a.v).slice(0, 4);
  const back = meta ? Math.round((meta.dtm[0] + meta.dtm[1]) / 2) : 90;

  return (
    <div className="space-y-4">
      <Card>
        <div className="mb-3"><CropPicker {...{ commodity, series, setCommodity, t }} /></div>
        <Eyebrow>{t("Which months pay best", "Aling buwan ang pinakamahal")}</Eyebrow>
        <p className="mb-3 text-xs leading-relaxed text-slate-600">
          {t(`${MONTHS_LONG.en[best.m - 1]} paid about ${best.pct}% above the year's average and ${MONTHS_LONG.en[worst.m - 1]} about ${Math.abs(worst.pct)}% below it.`,
             `Ang ${MONTHS_LONG.fil[best.m - 1]} ay mga ${best.pct}% mas mataas sa taunang katamtaman, ang ${MONTHS_LONG.fil[worst.m - 1]} ay mga ${Math.abs(worst.pct)}% mas mababa.`)}
        </p>
        <div className="h-48 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={vals} margin={{ top: 4, right: 6, bottom: 0, left: 0 }}>
              <CartesianGrid stroke="#e2e8f0" vertical={false} />
              <XAxis dataKey="label" tick={{ fontSize: 9, fill: "#64748b" }} interval={0} />
              <YAxis tick={{ fontSize: 9, fill: "#64748b" }} width={46} tickFormatter={(v) => `${v > 0 ? "+" : ""}${v}%`} />
              <ReferenceLine y={0} stroke="#94a3b8" />
              <Tooltip formatter={(v) => [`${v > 0 ? "+" : ""}${v}%`, t("vs year average", "vs taunang katamtaman")]}
                contentStyle={{ fontSize: 12 }} />
              <Bar dataKey="pct" radius={[2, 2, 0, 0]} isAnimationActive={false}>
                {vals.map((v) => (
                  <Cell key={v.m} fill={v.v >= 1.08 ? "#15803d" : v.v <= 0.92 ? "#b91c1c" : "#94a3b8"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
        <p className="mt-2 text-[11px] leading-relaxed text-slate-500">
          {t("Built from the published series: how each month compares with its own year's average. It repeats most years, but not every year.",
             "Mula sa nalathalang serye: paghahambing ng bawat buwan sa katamtaman ng sariling taon. Madalas umuulit, pero hindi laging.")}
        </p>
      </Card>

      <Card>
        <h2 className="mb-1 text-sm font-semibold text-slate-800">{t("Plant-back guide", "Gabay sa pagtatanim")}</h2>
        <p className="mb-3 text-xs text-slate-500">
          {t("To land a harvest in a high-price month, count back the growing period.",
             "Para umani sa mahal na buwan, bilangin pabalik ang haba ng tanim.")}
        </p>
        <table className="w-full text-right text-sm">
          <thead>
            <tr className="text-[10px] uppercase tracking-wider text-slate-500">
              <th className="py-2 text-left">{t("Harvest in", "Umani sa")}</th>
              <th className="py-2">{t("Usual lift", "Dagdag")}</th>
              <th className="py-2">{t("Plant around", "Itanim mga")}</th>
            </tr>
          </thead>
          <tbody>
            {top.map((o) => {
              const d = new Date(Date.UTC(new Date().getFullYear() + 1, o.m - 1, 15) - back * DAY);
              return (
                <tr key={o.m} className="border-t border-slate-100">
                  <td className="py-2 text-left">{MONTHS_LONG[lang][o.m - 1]}</td>
                  <td className={`py-2 font-semibold ${o.pct >= 0 ? "text-uc-green" : "text-slate-500"}`}>
                    {o.pct >= 0 ? "+" : ""}{o.pct}%
                  </td>
                  <td className="py-2">{t("early", "maagang")} {MONTHS_LONG[lang][d.getUTCMonth()]}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

/* ------------------------------- about ---------------------------- */

function AboutTab({ F, obs, meta, commodity, lang, t, user, signOut }) {
  const s = F.scores;
  const beats = [3, 6].filter((h) => s[h] && s[h].model < s[h].rw).length;
  const attribution = obs?.attribution;
  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-amber-300/70 bg-amber-50 p-4 text-sm leading-relaxed text-amber-900">
        <strong>{t("Read this first.", "Basahin muna ito.")}</strong>{" "}
        {t("These are predictions, not guarantees. Prices here are the Benguet province average published monthly by the PSA — not the price at your own trading post on your own day. Do not borrow money against these numbers.",
           "Mga hula ito, hindi garantiya. Ang presyo dito ay katamtaman ng buong Benguet na inilalathala buwan-buwan ng PSA — hindi ang presyo sa inyong trading post sa araw na iyon. Huwag mangutang batay sa mga numerong ito.")}
      </div>

      <Card>
        <h2 className="mb-2 text-sm font-semibold text-slate-800">{t("How good is the prediction?", "Gaano katumpak ang hula?")}</h2>
        <p className="mb-3 text-xs leading-relaxed text-slate-500">
          {t("Walk-forward back-test on this series, against two naive rules. Mean absolute error on log prices; lower is better.",
             "Pagsubok sa nakaraan ng seryeng ito laban sa dalawang simpleng patakaran. Mas mababa, mas mabuti.")}
        </p>
        <table className="w-full text-right text-sm tabular-nums">
          <thead>
            <tr className="text-[10px] uppercase tracking-wider text-slate-500">
              <th className="py-2 text-left">{t("Horizon", "Layo")}</th>
              <th className="py-2">{t("This model", "Modelo")}</th>
              <th className="py-2">{t("Last month", "Huling buwan")}</th>
              <th className="py-2">{t("Last year", "Nakaraang taon")}</th>
            </tr>
          </thead>
          <tbody>
            {[1, 3, 6, 12].filter((h) => s[h]).map((h) => (
              <tr key={h} className="border-t border-slate-100">
                <td className="py-2 text-left">{h} {t("mo", "buwan")}</td>
                <td className={`py-2 font-semibold ${s[h].model < s[h].rw ? "text-uc-green" : "text-slate-900"}`}>
                  {s[h].model.toFixed(3)}
                </td>
                <td className="py-2 text-slate-500">{s[h].rw?.toFixed(3) ?? "—"}</td>
                <td className="py-2 text-slate-500">{s[h].sn?.toFixed(3) ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-3 text-xs leading-relaxed text-slate-600">
          {t(`At 3 and 6 months ahead this model beats "same as last month" in ${beats} of 2 horizons for ${commodity}. At 1 month ahead it usually does not: for next month, trust the last published price over this app.`,
             `Sa 3 at 6 na buwan, nadaig ng modelo ang "pareho ng nakaraang buwan" sa ${beats} sa 2. Sa 1 buwan, kadalasan ay hindi: para sa susunod na buwan, mas mahusay ang huling nalathalang presyo.`)}
        </p>
      </Card>

      <Card>
        <h2 className="mb-2 text-sm font-semibold text-slate-800">
          {t("What is measured, and what is guessed", "Ano ang sinukat at ano ang hinulaan")}
        </h2>
        <ul className="space-y-2 text-xs leading-relaxed text-slate-600">
          <li><Pill tone="good">{t("Measured", "Sinukat")}</Pill>{" "}
            {t(`Monthly farmgate prices published by the PSA: ${F.nObs} observations, ${F.missing} missing.`,
               `Buwanang presyo sa bukid mula sa PSA: ${F.nObs} obserbasyon, ${F.missing} nawawala.`)}</li>
          <li><Pill tone="warn">{t("Modelled", "Hinulaan")}</Pill>{" "}
            {t("Every future price and every peso figure built from one. Seasonal pattern plus a damped trend, with error bands from back-testing.",
               "Lahat ng presyo sa hinaharap at lahat ng pisong galing dito.")}</li>
          <li><Pill tone="bad">{t("Interpolated", "Hinati-hati")}</Pill>{" "}
            {t("The daily curve. The PSA publishes nothing daily; it shows shape, never a real day's price.",
               "Ang linyang pang-araw. Walang inilalathalang araw-araw ang PSA.")}</li>
          <li><Pill tone="warn">{t("Assumed", "Ipinapalagay")}</Pill>{" "}
            {meta ? `${meta.dtmBasis}; ${meta.yieldBasis}.` : t("No crop calendar for this commodity — harvest window and volume are not shown.",
              "Walang kalendaryo para sa pananim na ito.")}</li>
        </ul>
      </Card>

      {attribution && (
        <Card>
          <h2 className="mb-2 text-sm font-semibold text-slate-800">{t("Source", "Pinagkunan")}</h2>
          <p className="text-[11px] leading-relaxed text-slate-500">
            {attribution.statement ?? attribution.text ?? JSON.stringify(attribution)}
          </p>
        </Card>
      )}

      <Card>
        <p className="text-xs text-slate-500">
          {user?.display_name} · {user?.role}
        </p>
        <button onClick={signOut} className="mt-2 rounded border border-slate-300 px-3 py-2 text-sm">
          {t("Sign out", "Mag-sign out")}
        </button>
      </Card>
    </div>
  );
}
