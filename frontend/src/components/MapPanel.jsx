import { useMemo, useState } from "react";
import Map, { Layer, Source, Popup, Marker, NavigationControl } from "react-map-gl/maplibre";
import "maplibre-gl/dist/maplibre-gl.css";
import { quantileBreaks } from "../lib/api";

/**
 * Municipal choropleth.
 *
 * MapLibre rather than Leaflet: the fill colour is driven by a data expression
 * over a GeoJSON source, which is awkward to do per-feature in Leaflet.
 *
 * Municipalities with no observation are rendered in a distinct hatched grey
 * and counted in the legend. An absent value must look different from a low
 * value — collapsing the two is how a map tells a lie.
 */

// Sequential pine-green ramp, light to dark; colourblind-safe ordering.
const RAMP = ["#e7f3ea", "#b7e0c2", "#7cc496", "#3f9d65", "#14532d"];
const NO_DATA = "#d4d4d8";

/** Bounding-box centre of a polygon. Good enough to hang a label on, and it
 *  needs no turf dependency or glyph server. */
function centre(geometry) {
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  const walk = (c) => {
    if (typeof c[0] === "number") {
      minX = Math.min(minX, c[0]); maxX = Math.max(maxX, c[0]);
      minY = Math.min(minY, c[1]); maxY = Math.max(maxY, c[1]);
    } else c.forEach(walk);
  };
  if (!geometry?.coordinates) return null;
  walk(geometry.coordinates);
  return [(minX + maxX) / 2, (minY + maxY) / 2];
}

export default function MapPanel({ featureCollection, unit, onSelect, selectedCode }) {
  const [hover, setHover] = useState(null);

  const { data, fillExpression, withoutData } = useMemo(() => {
    const features = featureCollection?.features ?? [];
    const values = features.map((f) => f.properties.value).filter((v) => v !== null);
    const breaks = quantileBreaks(values, RAMP.length);

    const steps = ["step", ["get", "value"], RAMP[0]];
    breaks.forEach((b, i) => steps.push(b, RAMP[i + 1]));

    const expression =
      values.length === 0
        ? NO_DATA
        : ["case", ["==", ["get", "value"], null], NO_DATA, steps];

    return {
      data: featureCollection ?? { type: "FeatureCollection", features: [] },
      fillExpression: expression,
      withoutData: features.filter((f) => !f.properties.has_data).length,
    };
  }, [featureCollection]);

  return (
    <div className="relative h-[460px] w-full overflow-hidden rounded-lg border border-slate-200">
      <Map
        initialViewState={{ longitude: 120.65, latitude: 16.55, zoom: 8.4 }}
        mapStyle={{
          version: 8,
          sources: {},
          layers: [{ id: "bg", type: "background", paint: { "background-color": "#f8fafc" } }],
        }}
        interactiveLayerIds={["municipality-fill"]}
        onMouseMove={(e) => setHover(e.features?.[0] ?? null)}
        onMouseLeave={() => setHover(null)}
        onClick={(e) => {
          const f = e.features?.[0];
          if (f) onSelect?.(f.properties.psgc_code);
        }}
        style={{ width: "100%", height: "100%" }}
      >
        <NavigationControl position="top-right" showCompass={false} />
        <Source id="municipalities" type="geojson" data={data}>
          <Layer
            id="municipality-fill"
            type="fill"
            paint={{ "fill-color": fillExpression, "fill-opacity": 0.85 }}
          />
          <Layer
            id="municipality-line"
            type="line"
            paint={{
              "line-color": ["case", ["==", ["get", "psgc_code"], selectedCode ?? ""], "#0f172a", "#ffffff"],
              "line-width": ["case", ["==", ["get", "psgc_code"], selectedCode ?? ""], 2.5, 0.8],
            }}
          />
        </Source>

        {(featureCollection?.features ?? []).map((f) => {
          const c = centre(f.geometry);
          if (!c) return null;
          return (
            <Marker key={f.properties.psgc_code} longitude={c[0]} latitude={c[1]}>
              <span className="pointer-events-none select-none whitespace-nowrap text-[10px] font-medium text-slate-800 [text-shadow:0_0_3px_#fff,0_0_3px_#fff,0_0_3px_#fff]">
                {f.properties.name}
              </span>
            </Marker>
          );
        })}

        {hover && (
          <Popup
            longitude={hover.geometry?.coordinates?.[0] ?? 120.65}
            latitude={hover.geometry?.coordinates?.[1] ?? 16.55}
            closeButton={false}
            className="text-xs"
          >
            <div className="font-semibold">{hover.properties.name}</div>
            <div>
              {hover.properties.value === null || hover.properties.value === undefined
                ? "no observation"
                : `${Number(hover.properties.value).toFixed(2)} ${unit ?? ""}`}
            </div>
            {hover.properties.quality_flag && hover.properties.quality_flag !== "ok" && (
              <div className="text-amber-700">flag: {hover.properties.quality_flag}</div>
            )}
          </Popup>
        )}
      </Map>

      <div className="absolute bottom-2 left-2 rounded bg-white/95 px-3 py-2 text-xs shadow">
        <div className="mb-1 font-medium text-slate-700">{unit ?? "value"}</div>
        <div className="flex items-center gap-1">
          {RAMP.map((c) => (
            <span key={c} className="h-3 w-6" style={{ backgroundColor: c }} />
          ))}
          <span className="ml-1 text-slate-500">low → high</span>
        </div>
        <div className="mt-1 flex items-center gap-1 text-slate-600">
          <span className="h-3 w-6" style={{ backgroundColor: NO_DATA }} />
          no observation ({withoutData})
        </div>
        <div className="mt-1 max-w-[18rem] text-[10px] leading-tight text-slate-500">
          Municipal polygons carrying a <strong>provincial</strong> price — PSA publishes no
          municipal figure, so every unit shades alike. Farm boundaries are not shown: no
          public parcel layer exists for Benguet.
        </div>
      </div>
    </div>
  );
}
