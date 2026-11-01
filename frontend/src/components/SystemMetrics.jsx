import React from 'react'
import { Gauge } from 'lucide-react'
import Panel from './Panel'
import { fixed, heading } from '../utils/format'

function Metric({ label, value, unit, hint, tone = 'default', emphasis = false }) {
  const toneClass =
    tone === 'good' ? 'text-emerald-700'
      : tone === 'warn' ? 'text-amber-700'
        : tone === 'bad' ? 'text-red-700' : 'text-slate-900'
  return (
    <div className="px-3 py-2 border-b border-r border-slate-200/70 min-w-0">
      <div className="metric-label truncate">{label}</div>
      <div className={`metric-value ${emphasis ? 'text-[15px]' : 'text-[13px]'} ${toneClass} truncate`}>
        {value}
        {unit ? <span className="text-[10px] text-slate-400 ml-1 font-sans font-semibold">{unit}</span> : null}
      </div>
      {hint ? <div className="text-3xs text-slate-400 truncate">{hint}</div> : null}
    </div>
  )
}

export default function SystemMetrics({ frame, summary, report }) {
  const f = frame || {}
  const ekfTone = f.ekf_error_m == null ? 'default' : f.ekf_error_m > 15 ? 'bad' : f.ekf_error_m > 5 ? 'warn' : 'good'
  return (
    <Panel
      title="System metrics"
      icon={Gauge}
      dense
      actions={
        <span className="text-3xs text-slate-400 font-mono">
          {summary?.samples ? `${summary.samples} frames · streaming` : 'awaiting data'}
        </span>
      }
    >
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6">
        <Metric label="Latitude" value={f.truth_lat != null ? f.truth_lat.toFixed(6) : '—'} unit="°" hint="ground truth" />
        <Metric label="Longitude" value={f.truth_lon != null ? f.truth_lon.toFixed(6) : '—'} unit="°" hint="ground truth" />
        <Metric label="Speed" value={fixed(f.speed_ms, 2)} unit="m/s" hint={f.speed_ms != null ? `${(f.speed_ms * 3.6).toFixed(0)} km/h` : ''} />
        <Metric label="Heading" value={heading(f.heading_deg)} hint={f.yaw_rate_dps != null ? `yaw ${f.yaw_rate_dps.toFixed(1)}°/s` : ''} />
        <Metric label="GNSS availability" value={fixed(summary?.gnss_availability_pct, 1)} unit="%" hint={f.gnss_available ? 'fix valid' : 'no fix'} tone={f.gnss_available ? 'good' : 'warn'} />
        <Metric label="Position error" value={fixed(f.ekf_error_m, 2)} unit="m" emphasis tone={ekfTone} hint={`DR ${fixed(f.dr_error_m, 1)} · RTS ${fixed(f.sm_error_m, 1)}`} />
        <Metric label="Estimated drift" value={fixed(f.drift_estimate_m, 2)} unit="m" hint={f.drift_rate_ms != null ? `rate ${f.drift_rate_ms.toFixed(2)} m/s` : ''} />
        <Metric label="EKF σ position" value={fixed(f.position_sigma_m, 2)} unit="m" hint={`√tr(P) ${fixed(f.uncertainty_m, 2)} m`} tone={f.position_sigma_m > 20 ? 'warn' : 'default'} />
        <Metric label="Raw GNSS error" value={fixed(f.gnss_error_m, 2)} unit="m" hint="vs ground truth" />
        <Metric label="Map offset" value={fixed(f.map_match?.offset_m, 2)} unit="m" hint={f.map_match?.matched ? f.map_match.road?.slice(0, 16) : 'no match'} />
        <Metric label="GNSS residual" value={fixed(f.gnss_residual_m, 2)} unit="m" hint={f.nis != null ? `NIS ${f.nis.toFixed(1)}` : ''} />
        <Metric label="Rejected fixes" value={f.rejected_count ?? 0} hint={`anomalies ${summary?.anomalies ?? 0}`} tone={f.rejected_count > 0 ? 'warn' : 'default'} />
      </div>
      <div className="px-3 py-1.5 text-3xs text-slate-400 border-t border-slate-200/70">
        σ is the 1σ radial scale from the EKF position covariance (largest eigenvalue); √tr(P) is a
        scale indicator, not a probability radius. RTS is the fixed-lag smoothed estimate (4 s behind
        the live solution).
      </div>
    </Panel>
  )
}
