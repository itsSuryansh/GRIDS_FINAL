import React, { useMemo, useState } from 'react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceArea,
  ReferenceLine,
} from 'recharts'
import { LineChart as LineIcon } from 'lucide-react'
import Panel from './Panel'
import { COLORS } from '../utils/format'

const AXIS = { fontSize: 9, fill: '#5d7cb1' }
const GRID = { stroke: COLORS.grid, strokeDasharray: '2 3' }

const TABS = [
  { id: 'error', label: 'Position error' },
  { id: 'residual', label: 'GNSS residual' },
  { id: 'velocity', label: 'Velocity' },
  { id: 'drift', label: 'Drift' },
  { id: 'uncertainty', label: 'EKF uncertainty' },
]

function ChartTooltip({ active, payload, label, unit }) {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-white border border-navy-200 rounded shadow-card px-2 py-1.5 text-2xs">
      <div className="font-semibold text-navy-800 mb-0.5">t = {Number(label).toFixed(1)} s</div>
      {payload.map((p) => (
        <div key={p.dataKey} className="flex items-center gap-1.5">
          <span className="inline-block h-1.5 w-3 rounded" style={{ background: p.color }} />
          <span className="text-navy-500">{p.name}</span>
          <span className="ml-auto font-mono text-navy-900">
            {p.value == null ? '—' : Number(p.value).toFixed(2)} {unit}
          </span>
        </div>
      ))}
    </div>
  )
}

export default function LiveCharts({ trail, outage }) {
  const [tab, setTab] = useState('error')

  const data = useMemo(() => {
    const stride = Math.max(1, Math.floor(trail.length / 400))
    return trail.filter((_, i) => i % stride === 0).map((f) => ({
      t: Number(f.t.toFixed(2)),
      ekf_error_m: f.ekf_error_m,
      dr_error_m: f.dr_error_m,
      gnss_error_m: f.gnss_error_m,
      gnss_residual_m: f.gnss_residual_m,
      speed_ms: f.speed_ms,
      drift_m: f.drift_estimate_m,
      uncertainty_m: f.uncertainty_m,
      anomaly_score: f.anomaly_score != null ? f.anomaly_score * 100 : null,
      gnss_unavailable: f.gnss_status === 'unavailable',
    }))
  }, [trail])

  const outageZones = useMemo(() => {
    // derive contiguous unavailable windows from the stream itself
    const zones = []
    let start = null
    data.forEach((d) => {
      if (d.gnss_unavailable && start === null) start = d.t
      if (!d.gnss_unavailable && start !== null) {
        zones.push([start, d.t])
        start = null
      }
    })
    if (start !== null) zones.push([start, data[data.length - 1]?.t ?? start])
    return zones
  }, [data])

  const anomalyMarks = useMemo(
    () => data.filter((d) => d.anomaly_score != null && d.anomaly_score > 45).slice(-25),
    [data],
  )

  const common = (
    <>
      {GRID && <CartesianGrid {...GRID} />}
      <XAxis dataKey="t" tick={AXIS} tickLine={false} axisLine={{ stroke: COLORS.grid }} unit="s" minTickGap={28} />
      <Tooltip content={<ChartTooltip unit="m" />} />
      {outageZones.map(([a, b], i) => (
        <ReferenceArea key={`oz-${i}`} x1={a} x2={b} fill="#93a8cd" fillOpacity={0.12} />
      ))}
    </>
  )

  return (
    <Panel
      title="Live analytics"
      icon={LineIcon}
      actions={
        <div className="flex gap-0.5 flex-wrap justify-end">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`tab !px-1.5 !py-0.5 !text-[10px] ${tab === t.id ? 'tab-active' : ''}`}
            >
              {t.label}
            </button>
          ))}
        </div>
      }
    >
      <div className="h-[188px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          {tab === 'error' ? (
            <LineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -18 }}>
              {common}
              <YAxis tick={AXIS} tickLine={false} axisLine={false} width={44} />
              <Line type="monotone" dataKey="ekf_error_m" name="EKF" stroke={COLORS.ekf} dot={false} strokeWidth={1.8} isAnimationActive={false} />
              <Line type="monotone" dataKey="dr_error_m" name="Dead reckoning" stroke={COLORS.dr} dot={false} strokeWidth={1.3} isAnimationActive={false} />
              <Line type="monotone" dataKey="gnss_error_m" name="GNSS" stroke={COLORS.gnss} dot={false} strokeWidth={1.2} strokeDasharray="4 2" isAnimationActive={false} connectNulls={false} />
            </LineChart>
          ) : tab === 'residual' ? (
            <LineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -18 }}>
              {common}
              <YAxis tick={AXIS} tickLine={false} axisLine={false} width={44} />
              <ReferenceLine y={10} stroke="#c98a05" strokeDasharray="3 3" strokeWidth={1} />
              <Line type="monotone" dataKey="gnss_residual_m" name="GNSS residual" stroke={COLORS.gnss} dot={false} strokeWidth={1.5} isAnimationActive={false} />
              <Line type="monotone" dataKey="anomaly_score" name="Anomaly score %" stroke={COLORS.anomaly} dot={false} strokeWidth={1} strokeDasharray="3 2" isAnimationActive={false} />
            </LineChart>
          ) : tab === 'velocity' ? (
            <LineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -18 }}>
              {common}
              <YAxis tick={AXIS} tickLine={false} axisLine={false} width={44} />
              <Line type="monotone" dataKey="speed_ms" name="Speed" stroke={COLORS.ekf} dot={false} strokeWidth={1.6} isAnimationActive={false} />
            </LineChart>
          ) : tab === 'drift' ? (
            <LineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -18 }}>
              {common}
              <YAxis tick={AXIS} tickLine={false} axisLine={false} width={44} />
              <Line type="monotone" dataKey="drift_m" name="DR/EKF separation" stroke={COLORS.dr} dot={false} strokeWidth={1.6} isAnimationActive={false} />
              <Line type="monotone" dataKey="dr_error_m" name="DR error vs truth" stroke={COLORS.truth} dot={false} strokeWidth={1} strokeDasharray="3 2" isAnimationActive={false} />
            </LineChart>
          ) : (
            <LineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -18 }}>
              {common}
              <YAxis tick={AXIS} tickLine={false} axisLine={false} width={44} />
              <Line type="monotone" dataKey="uncertainty_m" name="√tr(P)" stroke={COLORS.cyan} dot={false} strokeWidth={1.6} isAnimationActive={false} />
              <Line type="monotone" dataKey="ekf_error_m" name="Actual error" stroke={COLORS.ekf} dot={false} strokeWidth={1.1} strokeDasharray="3 2" isAnimationActive={false} />
            </LineChart>
          )}
        </ResponsiveContainer>
      </div>
      <div className="mt-1 flex items-center justify-between text-2xs text-navy-400">
        <span>
          shaded = GNSS unavailable ·{' '}
          {outage?.start_s != null ? `configured outage ${outage.start_s.toFixed(0)}–${outage.end_s.toFixed(0)} s` : 'no outage configured'}
        </span>
        <span className="font-mono">{data.length} pts</span>
      </div>
    </Panel>
  )
}
