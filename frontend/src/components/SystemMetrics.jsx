import React from 'react'
import { Gauge } from 'lucide-react'
import Panel from './Panel'
import { fixed, heading, latlon, metres } from '../utils/format'

function Metric({ label, value, unit, hint, emphasis = false, tone = 'default' }) {
  const toneClass =
    tone === 'good' ? 'text-emerald-700'
      : tone === 'warn' ? 'text-amber-700'
        : tone === 'bad' ? 'text-red-700' : 'text-navy-900'
  return (
    <div className="px-3 py-2 border-b border-r border-navy-100 last:border-r-0 min-w-0">
      <div className="metric-label truncate">{label}</div>
      <div className={`metric-value ${emphasis ? 'text-base' : 'text-sm'} ${toneClass} truncate`}>
        {value}
        {unit ? <span className="text-2xs text-navy-400 ml-1 font-sans font-medium">{unit}</span> : null}
      </div>
      {hint ? <div className="text-2xs text-navy-400 truncate">{hint}</div> : null}
    </div>
  )
}

export default function SystemMetrics({ frame, summary }) {
  const f = frame || {}
  const ekfTone = f.ekf_error_m == null ? 'default' : f.ekf_error_m > 15 ? 'bad' : f.ekf_error_m > 5 ? 'warn' : 'good'
  const sig = f.position_sigma_m
  const unc = f.uncertainty_m

  return (
    <Panel
      title="System metrics"
      icon={Gauge}
      dense
      actions={
        <span className="text-2xs text-navy-400 font-mono">
          {summary?.samples ? `${summary.samples} frames` : 'no data'}
        </span>
      }
    >
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-4">
        <Metric label="Latitude" value={f.truth_lat != null ? f.truth_lat.toFixed(6) : '—'} unit="°" hint="ground truth" />
        <Metric label="Longitude" value={f.truth_lon != null ? f.truth_lon.toFixed(6) : '—'} unit="°" hint="ground truth" />
        <Metric label="Speed" value={fixed(f.speed_ms, 2)} unit="m/s" hint={f.speed_ms != null ? `${(f.speed_ms * 3.6).toFixed(1)} km/h` : ''} />
        <Metric label="Heading" value={heading(f.heading_deg)} hint={f.yaw_rate_dps != null ? `yaw ${f.yaw_rate_dps.toFixed(1)}°/s` : ''} />
        <Metric
          label="GNSS availability"
          value={summary?.gnss_availability_pct != null ? fixed(summary.gnss_availability_pct, 1) : '—'}
          unit="%"
          hint={f.gnss_available ? 'fix available' : 'no fix'}
          tone={f.gnss_available ? 'good' : 'warn'}
        />
        <Metric
          label="Position error"
          value={fixed(f.ekf_error_m, 2)}
          unit="m"
          emphasis
          tone={ekfTone}
          hint={`DR ${fixed(f.dr_error_m, 1)} m · GNSS ${fixed(f.gnss_error_m, 1)} m`}
        />
        <Metric
          label="Estimated drift"
          value={fixed(f.drift_estimate_m, 2)}
          unit="m"
          hint={f.drift_rate_ms != null ? `rate ${f.drift_rate_ms.toFixed(2)} m/s` : ''}
        />
        <Metric
          label="EKF σ (position)"
          value={fixed(sig, 2)}
          unit="m"
          hint={`√tr(P) = ${fixed(unc, 2)} m`}
          tone={sig != null && sig > 20 ? 'warn' : 'default'}
        />
      </div>
      <div className="px-3 py-1.5 text-2xs text-navy-400 border-t border-navy-100">
        1σ position uncertainty from the EKF covariance (largest eigenvalue of the EN block); √tr(P) is a
        scale indicator, not a confidence radius.
      </div>
    </Panel>
  )
}
