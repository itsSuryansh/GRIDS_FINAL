/** Formatting helpers shared by the dashboard components. */

export function fixed(value, digits = 1, dash = '—') {
  if (value === null || value === undefined || Number.isNaN(value)) return dash
  return Number(value).toFixed(digits)
}

export function metres(value, digits = 1) {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return `${Number(value).toFixed(digits)} m`
}

export function seconds(value, digits = 1) {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return `${Number(value).toFixed(digits)} s`
}

export function latlon(lat, lon) {
  if (lat === null || lat === undefined || lon === null || lon === undefined) return '—'
  return `${Number(lat).toFixed(6)}, ${Number(lon).toFixed(6)}`
}

export function heading(deg) {
  if (deg === null || deg === undefined) return '—'
  const d = ((Number(deg) % 360) + 360) % 360
  const dirs = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
  const idx = Math.round(d / 45) % 8
  return `${d.toFixed(0)}° ${dirs[idx]}`
}

export function clockFromSeconds(t) {
  if (t === null || t === undefined) return '00:00.0'
  const m = Math.floor(t / 60)
  const s = t - m * 60
  return `${String(m).padStart(2, '0')}:${s.toFixed(1).padStart(4, '0')}`
}

/** Colour tokens used consistently across map / charts / legend. */
export const COLORS = {
  truth: '#121d35',
  gnss: '#c98a05',
  dr: '#7c3aed',
  ekf: '#1d4ed8',
  ml: '#0891b2',
  anomaly: '#c02b45',
  outage: '#93a8cd',
  grid: '#e3e9f4',
}

export const STATUS_STYLES = {
  healthy: 'bg-emerald-50 text-emerald-700 border border-emerald-200',
  degraded: 'bg-amber-50 text-amber-700 border border-amber-200',
  unavailable: 'bg-navy-100 text-navy-500 border border-navy-200',
  suspicious: 'bg-red-50 text-red-700 border border-red-200',
}

export const MODULE_STYLES = {
  active: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  degraded: 'bg-amber-50 text-amber-700 border-amber-200',
  coasting: 'bg-sky-50 text-sky-700 border-sky-200',
  rejected: 'bg-red-50 text-red-700 border-red-200',
  alert: 'bg-red-50 text-red-700 border-red-200',
  unavailable: 'bg-navy-100 text-navy-500 border-navy-200',
  idle: 'bg-navy-50 text-navy-500 border-navy-200',
  'n/a': 'bg-navy-50 text-navy-400 border-navy-200',
}
