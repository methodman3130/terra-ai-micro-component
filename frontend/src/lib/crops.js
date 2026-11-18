/**
 * Agronomic constants for the farmer view.
 *
 * Every figure here is cited. Where no Benguet-specific published figure was
 * found, the entry is marked `indicative: true` and the view renders it with a
 * caveat rather than silently presenting a guess as a measurement. Days are
 * from planting or transplanting as the cited guide counts them; the view says
 * which, because a 90-day crop counted from emergence is not a 90-day crop
 * counted from sowing.
 */
export const CROPS = {
  Cabbage: {
    fil: "Repolyo",
    dtm: [75, 100],
    dtmBasis: "ATI-CAR, Cabbage Production — maturity 75–100 days",
    yieldKgHa: 22000,
    yieldBasis: "BSU 2022, Benguet highland vegetables (2019 baseline survey)",
  },
  Carrot: {
    fil: "Karot",
    dtm: [90, 120],
    dtmBasis: "DA, Carrot Production Guide — 90–120 days after emergence",
    yieldKgHa: 20000,
    yieldBasis: "BSU 2022, Benguet highland vegetables (2019 baseline survey)",
  },
  Potato: {
    fil: "Patatas",
    dtm: [90, 120],
    dtmBasis: "DA-AMIA, Benguet blight-tolerant potato — Solibao 90–120 days",
    yieldKgHa: 16000,
    yieldBasis: "BSU 2022, Benguet highland vegetables (2019 baseline survey)",
  },
  "Chinese cabbage (Wongbok, Pechay Baguio)": {
    fil: "Pechay Baguio (Wongbok)",
    dtm: [60, 80],
    dtmBasis: "Indicative — no DA-CAR figure located for Wongbok",
    dtmIndicative: true,
    yieldKgHa: 17000,
    yieldBasis: "BSU 2022, Benguet highland vegetables (2019 baseline survey)",
  },
  Lettuce: {
    fil: "Litsugas",
    dtm: [55, 60],
    dtmBasis: "DA-CAR organic highland technoguide — head lettuce 55–60 days",
    yieldKgHa: 15000,
    yieldBasis: "Indicative — no published Benguet yield located",
    yieldIndicative: true,
  },
};

/** The register's commodity labels carry leading dots and parenthetical
 *  synonyms; match on the meaningful part rather than on exact equality. */
export function cropMeta(commodity) {
  if (!commodity) return null;
  if (CROPS[commodity]) return CROPS[commodity];
  const norm = String(commodity).replace(/^\.+/, "").trim().toLowerCase();
  for (const [k, v] of Object.entries(CROPS)) {
    if (k.toLowerCase() === norm) return v;
  }
  if (norm.includes("wongbok") || norm.includes("pechay baguio")) {
    return CROPS["Chinese cabbage (Wongbok, Pechay Baguio)"];
  }
  for (const [k, v] of Object.entries(CROPS)) {
    if (norm.startsWith(k.toLowerCase())) return v;
  }
  return null;
}
