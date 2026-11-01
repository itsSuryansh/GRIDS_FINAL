/**
 * REST client. Uses relative URLs so the same build works behind the Vite dev
 * proxy, inside Docker Compose, and in hosted preview environments.
 */
const BASE = import.meta.env.VITE_API_BASE || '/api'

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      if (body?.detail) {
        detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
      }
    } catch {
      /* keep status text */
    }
    throw new Error(detail)
  }
  if (res.status === 204) return null
  return res.json()
}

export const api = {
  health: () => request('/health'),
  systemInfo: () => request('/system/info'),

  scenarios: () => request('/simulation/scenarios'),
  patterns: () => request('/simulation/patterns'),
  status: () => request('/simulation/status'),
  start: (config) =>
    request('/simulation/start', { method: 'POST', body: JSON.stringify(config) }),
  pause: () => request('/simulation/pause', { method: 'POST' }),
  resume: () => request('/simulation/resume', { method: 'POST' }),
  stop: () => request('/simulation/stop', { method: 'POST' }),
  reset: () => request('/simulation/reset', { method: 'POST' }),

  current: () => request('/navigation/current'),
  history: (limit = 800, stride = 1) =>
    request(`/navigation/history?limit=${limit}&stride=${stride}`),
  route: () => request('/navigation/route'),
  anomalies: () => request('/navigation/anomalies'),
  modules: () => request('/navigation/modules'),
  smoothed: () => request('/navigation/smoothed'),

  summary: () => request('/analytics/summary'),
  compare: (series = true) => request(`/analytics/compare?include_series=${series}`),
  mlStatus: () => request('/analytics/ml'),
  sessions: (limit = 30) => request(`/analytics/sessions?limit=${limit}`),
  session: (id) => request(`/analytics/sessions/${id}`),
  wsStatus: () => request('/ws/status'),

  mapStatus: () => request('/map/status'),
  mapRoads: (lat, lon, radius = 1500) =>
    request(`/map/roads?lat=${lat}&lon=${lon}&radius_m=${radius}`),
  prefetchTiles: (lat, lon) =>
    request(`/map/prefetch?lat=${lat}&lon=${lon}`, { method: 'POST' }),
  tileUrl: (z, x, y) => `${BASE}/map/tile/${z}/${x}/${y}.png`,
}

export default api
