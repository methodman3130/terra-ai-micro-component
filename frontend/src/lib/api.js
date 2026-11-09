const BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

// Held in a module variable so no component has to thread it through props.
let token = null;
export const setToken = (t) => { token = t; };
export const getToken = () => token;

async function call(path, { method = "GET", body } = {}) {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: {
      ...(body ? { "Content-Type": "application/json" } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  if (!res.ok) {
    // FastAPI puts the useful message in `detail`; surface that rather than a
    // bare status code, which tells the user nothing actionable.
    let detail = "";
    try {
      const data = await res.json();
      detail = typeof data.detail === "string"
        ? data.detail
        : Array.isArray(data.detail)
          ? data.detail.map((d) => d.msg).join("; ")
          : "";
    } catch { /* non-JSON error body */ }
    throw new Error(detail || `${res.status} ${res.statusText}`);
  }
  return res.json();
}

const get = (path) => call(path);

export const api = {
  register: (email, display_name, password) =>
    call("/auth/register", { method: "POST", body: { email, display_name, password } }),
  login: (email, password) =>
    call("/auth/login", { method: "POST", body: { email, password } }),
  logout: () => call("/auth/logout", { method: "POST" }),
  me: () => get("/auth/me"),
  users: () => get("/auth/users"),
  setRole: (id, role) => call(`/auth/users/${id}/role`, { method: "PATCH", body: { role } }),
  setActive: (id, active) =>
    call(`/auth/users/${id}/active?active=${active}`, { method: "PATCH" }),
  notice: () => get("/notice"),
  health: () => get("/health"),
  provenance: () => get("/provenance"),
  series: (params = {}) => {
    const q = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== "")
    );
    return get(`/series${q.toString() ? `?${q}` : ""}`);
  },
  observations: (seriesId) => get(`/series/${encodeURIComponent(seriesId)}/observations`),
  municipalities: (params = {}) => {
    const q = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== "")
    );
    return get(`/geo/municipalities${q.toString() ? `?${q}` : ""}`);
  },
  benchmark: (seriesId) => get(`/benchmark/${encodeURIComponent(seriesId)}`),
  protocol: () => get("/benchmark/protocol"),
};

/** Quantile breaks. Equal-interval would be misleading on a skewed price
 *  distribution, which Benguet farmgate prices very much are. */
export function quantileBreaks(values, n = 5) {
  const sorted = values.filter((v) => v !== null && Number.isFinite(v)).sort((a, b) => a - b);
  if (sorted.length === 0) return [];
  const breaks = [];
  for (let i = 1; i < n; i += 1) {
    const idx = Math.floor((i / n) * (sorted.length - 1));
    breaks.push(sorted[idx]);
  }
  return [...new Set(breaks)];
}
