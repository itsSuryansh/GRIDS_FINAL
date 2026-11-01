import React, { useMemo, useState } from 'react'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  ReferenceArea, ReferenceLine, Legend,
} from 'recharts'
import { LineChart as LineIcon } from 'lucide-react'
import Panel from './Panel'
import { COLORS } from '../utils/format'

const AXIS = { fontSize: 9, fill: '#94a3b8', fontFamily: 'JetBrains Mono Variable, monospace' }
const GRID = { stroke: 'rgba(148,163,184,0.22)', strokeDasharray: '2 4' }

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
    <div className="bg-white/97 backdrop-blur-md border border-slate-200 rounded-lg shadow-float px-2.5 py-2 min-w-[148px]">
      <div className="font-mono text-[9.5px] uppercase tracking-[0.08em] text-slate-400 mb-1 pb-1 border-b border-slate-100">
        t = {Number(label).toFixed(1)} s
      </div>
      {payload.map((p) => (
        <div key={p.dataKey} className="flex items-center gap-1.5 leading-[1.4]">
          <span className="inline-block h-[2px] w-2.5 rounded-full" style={{ background: p.color }} />
          <span className="text-[10px] text-slate-500">{p.name}</span>
          <span className="ml-auto font-mono text-[10.5px] font-semibold text-slate-900 tabular-nums">
            {p.value == null ? '—' : Number(p.value).toFixed(2)}
            <span className="text-[8.5px] text-slate-400 ml-0.5 font-normal">{unit}</span>
          </span>
        </div>
      ))}
    </div>
  )
}

export default function LiveCharts({ trail, outage }) {
  const [tab, setTab] = useState('error')

  const data = useMemo(() => {
    const stride = Math.max(1, Math.floor(trail.length / 420))
    return trail.filter((_, i) => i % stride === 0).map((f) => ({
      t: Number(f.t.toFixed(2)),
      ekf_error_m: f.ekf_error_m,
      dr_error_m: f.dr_error_m,
      gnss_error_m: f.gnss_error_m,
      sm_error_m: f.sm_error_m,
      nomap_error_m: f.nomap_error_m,
      gnss_residual_m: f.gnss_residual_m,
      speed_ms: f.speed_ms,
      drift_m: f.drift_estimate_m,
      uncertainty_m: f.uncertainty_m,
      anomaly_score: f.anomaly_score != null ? f.anomaly_score * 100 : null,
      gnss_unavailable: f.gnss_status === 'unavailable',
    }))
  }, [trail])

  const outageZones = useMemo(() => {
    const zones = []
    let start = null
    data.forEach((d) => {
      if (d.gnss_unavailable && start === null) start = d.t
      if (!d.gnss_unavailable && start !== null) { zones.push([start, d.t]); start = null }
    })
    if (start !== null) zones.push([start, data[data.length - 1]?.t ?? start])
    return zones
  }, [data])

  const common = (
    <>
      <CartesianGrid {...GRID} />
      <XAxis
        dataKey="t"
        tick={AXIS}
        tickLine={false}
        axisLine={{ stroke: 'rgba(148,163,184,0.35)' }}
        tickMargin={4}
        unit="s"
        minTickGap={34}
      />
      <Tooltip content={<ChartTooltip unit="m" />} />
      <Legend wrapperStyle={{ fontSize: 9.5, paddingTop: 2 }} iconSize={7} iconType="plainline" />
      {outageZones.map(([a, b], i) => (
        <ReferenceArea key={`oz-${i}`} x1={a} x2={b} fill="#64748b" fillOpacity={0.08} />
      ))}
    </>
  )

  return (
    <Panel
      title="Live analytics"
      icon={LineIcon}
      actions={
        <div className="flex gap-[2px] rounded-lg bg-slate-100/90 p-[2px]">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`px-2 py-[3px] rounded-md text-[10px] font-semibold transition-all duration-150 ${
                tab === t.id
                  ? 'bg-white text-slate-900 shadow-[0_1px_2px_rgba(15,23,42,0.13)]'
                  : 'text-slate-500 hover:text-slate-800'
              }`}
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
            <LineChart data={data} margin={{ top: 6, right: 14, bottom: 2, left: 0 }}>
              {common}
              <YAxis tick={AXIS} tickLine={false} axisLine={false} width={44} tickMargin={4} />
              <Line type="monotone" dataKey="ekf_error_m" name="EKF" stroke={COLORS.ekf} dot={false} strokeWidth={1.8} isAnimationActive={false} />
              <Line type="monotone" dataKey="sm_error_m" name="RTS" stroke={COLORS.smoothed} dot={false} strokeWidth={1.4} isAnimationActive={false} connectNulls />
              <Line type="monotone" dataKey="dr_error_m" name="DR" stroke={COLORS.dr} dot={false} strokeWidth={1.2} isAnimationActive={false} />
              <Line type="monotone" dataKey="gnss_error_m" name="GNSS" stroke={COLORS.gnss} dot={false} strokeWidth={1} strokeDasharray="4 2" isAnimationActive={false} connectNulls={false} />
            </LineChart>
          ) : tab === 'residual' ? (
            <LineChart data={data} margin={{ top: 6, right: 14, bottom: 2, left: 0 }}>
              {common}
              <YAxis tick={AXIS} tickLine={false} axisLine={false} width={44} tickMargin={4} />
              <ReferenceLine y={6} stroke="#d97706" strokeDasharray="3 3" strokeWidth={1} />
              <Line type="monotone" dataKey="gnss_residual_m" name="GNSS residual" stroke={COLORS.gnss} dot={false} strokeWidth={1.5} isAnimationActive={false} />
              <Line type="monotone" dataKey="anomaly_score" name="Anomaly score %" stroke={COLORS.anomaly} dot={false} strokeWidth={1} strokeDasharray="3 2" isAnimationActive={false} />
            </LineChart>
          ) : tab === 'velocity' ? (
            <LineChart data={data} margin={{ top: 6, right: 14, bottom: 2, left: 0 }}>
              {common}
              <YAxis tick={AXIS} tickLine={false} axisLine={false} width={44} tickMargin={4} />
              <Line type="monotone" dataKey="speed_ms" name="Fused speed" stroke={COLORS.ekf} dot={false} strokeWidth={1.6} isAnimationActive={false} />
            </LineChart>
          ) : tab === 'drift' ? (
            <LineChart data={data} margin={{ top: 6, right: 14, bottom: 2, left: 0 }}>
              {common}
              <YAxis tick={AXIS} tickLine={false} axisLine={false} width={44} tickMargin={4} />
              <Line type="monotone" dataKey="drift_m" name="DR/EKF separation" stroke={COLORS.dr} dot={false} strokeWidth={1.6} isAnimationActive={false} />
              <Line type="monotone" dataKey="dr_error_m" name="DR error vs truth" stroke={COLORS.truth} dot={false} strokeWidth={1} strokeDasharray="3 2" isAnimationActive={false} />
            </LineChart>
          ) : (
            <LineChart data={data} margin={{ top: 6, right: 14, bottom: 2, left: 0 }}>
              {common}
              <YAxis tick={AXIS} tickLine={false} axisLine={false} width={44} tickMargin={4} />
              <Line type="monotone" dataKey="uncertainty_m" name="√tr(P)" stroke={COLORS.smoothed} dot={false} strokeWidth={1.6} isAnimationActive={false} />
              <Line type="monotone" dataKey="ekf_error_m" name="Actual error" stroke={COLORS.ekf} dot={false} strokeWidth={1.1} strokeDasharray="3 2" isAnimationActive={false} />
            </LineChart>
          )}
        </ResponsiveContainer>
      </div>
      <div className="mt-1.5 pt-1.5 border-t border-slate-100 flex items-center justify-between text-[9.5px] text-slate-400">
        <span>
          shaded = GNSS unavailable ·{' '}
          {outage?.start_s != null ? `outage ${outage.start_s.toFixed(0)}–${outage.end_s?.toFixed(0)} s` : 'no outage configured'}
        </span>
        <span className="font-mono tabular-nums">{data.length} pts · {TABS.find((t) => t.id === tab)?.label.toLowerCase()}</span>
      </div>
    </Panel>
  )
}
