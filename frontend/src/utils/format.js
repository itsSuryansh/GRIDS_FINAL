/** Formatting + design tokens shared across the dashboard. */

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

export function latlon(lat, lon, digits = 6) {
  if (lat === null || lat === undefined || lon === null || lon === undefined) return '—'
  return `${Number(lat).toFixed(digits)}, ${Number(lon).toFixed(digits)}`
}

export function heading(deg) {
  if (deg === null || deg === undefined) return '—'
  const d = ((Number(deg) % 360) + 360) % 360
  const dirs = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
  return `${d.toFixed(0)}° ${dirs[Math.round(d / 45) % 8]}`
}

export function clockFromSeconds(t) {
  if (t === null || t === undefined) return '00:00.0'
  const m = Math.floor(t / 60)
  const s = t - m * 60
  return `${String(m).padStart(2, '0')}:${s.toFixed(1).padStart(4, '0')}`
}

/** Colour tokens used consistently across map / charts / legend / tables. */
export const COLORS = {
  truth: '#0f172a',
  gnss: '#d97706',
  dr: '#7c3aed',
  ekf: '#1d4ed8',
  ekfNomap: '#93a8cd',
  smoothed: '#0d9488',
  ml: '#0891b2',
  anomaly: '#dc2626',
  outage: '#64748b',
  grid: '#e2e8f0',
}

export const ALGO_META = {
  gnss: { label: 'GNSS (raw)', short: 'GNSS', color: COLORS.gnss },
  dead_reckoning: { label: 'Dead reckoning', short: 'DR', color: COLORS.dr },
  ekf_nomap: { label: 'EKF · no map aiding', short: 'EKF−map', color: COLORS.ekfNomap },
  ekf: { label: 'EKF fusion (GRIDS)', short: 'EKF', color: COLORS.ekf },
  ekf_ml: { label: 'EKF + ML correction', short: 'EKF+ML', color: COLORS.ml },
  rts_smoothed: { label: 'RTS smoothed (post-processed)', short: 'RTS', color: COLORS.smoothed },
}

export const STATUS_STYLES = {
  healthy: 'bg-emerald-50 text-emerald-700 border border-emerald-200',
  degraded: 'bg-amber-50 text-amber-700 border border-amber-200',
  unavailable: 'bg-slate-100 text-slate-500 border border-slate-200',
  suspicious: 'bg-red-50 text-red-700 border border-red-200',
}

export const MODULE_STYLES = {
  active: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  degraded: 'bg-amber-50 text-amber-700 border-amber-200',
  coasting: 'bg-sky-50 text-sky-700 border-sky-200',
  rejected: 'bg-red-50 text-red-700 border-red-200',
  alert: 'bg-red-50 text-red-700 border-red-200',
  off: 'bg-slate-100 text-slate-500 border-slate-200',
  unavailable: 'bg-slate-100 text-slate-500 border-slate-200',
  idle: 'bg-slate-50 text-slate-500 border-slate-200',
  'warming up': 'bg-sky-50 text-sky-700 border-sky-200',
  'n/a': 'bg-slate-50 text-slate-400 border-slate-200',
}
