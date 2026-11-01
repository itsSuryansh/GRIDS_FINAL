import React from 'react'
import { Satellite, ShieldAlert, ShieldCheck, ShieldX, Clock } from 'lucide-react'
import Panel from './Panel'
import { STATUS_STYLES, fixed, seconds } from '../utils/format'

function Row({ label, value, mono = true, tone = '' }) {
  return (
    <div className="flex items-baseline justify-between gap-2 py-1 border-b border-navy-50 last:border-0">
      <span className="metric-label">{label}</span>
      <span className={`text-xs ${mono ? 'font-mono tabular-nums' : ''} ${tone || 'text-navy-900'} text-right`}>
        {value}
      </span>
    </div>
  )
}

const SHIELD = {
  healthy: { icon: ShieldCheck, cls: 'text-emerald-600' },
  degraded: { icon: ShieldAlert, cls: 'text-amber-600' },
  suspicious: { icon: ShieldX, cls: 'text-red-600' },
  unavailable: { icon: Satellite, cls: 'text-navy-400' },
}

export default function GnssStatusPanel({ frame, summary, anomalies, status }) {
  const f = frame || {}
  const st = f.gnss_status || 'unavailable'
  const shield = SHIELD[st] || SHIELD.unavailable
  const ShieldIcon = shield.icon
  const mode = st === 'unavailable' ? 'absent' : f.anomaly ? (st === 'suspicious' ? 'suspended' : 'nominal' ) : 'nominal'
  const timeSinceFix =
    status?.sim_time != null && frame?.t != null && f.gnss_available ? 0 : null

  return (
    <Panel
      title="GNSS channel"
      icon={Satellite}
      actions={
        <span className={`chip ${STATUS_STYLES[st] || STATUS_STYLES.unavailable}`}>
          <ShieldIcon size={10} /> {st}
        </span>
      }
    >
      <div className="grid grid-cols-2 gap-x-3">
        <Row label="Signal status" value={st} mono={false} />
        <Row label="Fix valid" value={f.gnss_available ? 'yes' : 'no'} tone={f.gnss_available ? 'text-emerald-700' : 'text-amber-700'} />
        <Row label="Residual" value={f.gnss_residual_m != null ? `${f.gnss_residual_m.toFixed(1)} m` : '—'} />
        <Row
          label="Anomaly score"
          value={f.anomaly_score != null ? `${(f.anomaly_score * 100).toFixed(0)} %` : '—'}
          tone={f.anomaly ? 'text-red-700' : 'text-navy-900'}
        />
        <Row label="NIS" value={f.nis != null ? f.nis.toFixed(1) : '—'} />
        <Row label="Raw GNSS err." value={f.gnss_error_m != null ? `${f.gnss_error_m.toFixed(1)} m` : '—'} />
        <Row label="Rejected fixes" value={f.rejected_count ?? 0} tone={f.rejected_count > 0 ? 'text-red-700' : ''} />
        <Row label="Detector state" value={f.anomaly ? 'alert' : mode} mono={false} />
      </div>

      {f.anomaly_reason && (
        <div className={`mt-2 rounded border px-2 py-1.5 text-2xs leading-snug ${f.anomaly ? 'border-red-200 bg-red-50 text-red-800' : 'border-navy-100 bg-navy-50 text-navy-600'}`}>
          <span className="font-semibold uppercase tracking-wider mr-1">
            {f.anomaly ? f.anomaly_type : 'detector'}
          </span>
          {f.anomaly_reason}
        </div>
      )}

      {f.anomaly_severities && f.anomaly ? (
        <div className="mt-1.5 grid grid-cols-5 gap-1">
          {Object.entries(f.anomaly_severities).map(([k, v]) => (
            <div key={k} className="text-center">
              <div className="h-1 rounded bg-navy-100 overflow-hidden">
                <div
                  className="h-full"
                  style={{
                    width: `${Math.min(100, v * 100)}%`,
                    background: v > 0.85 ? '#c02b45' : v > 0.45 ? '#c98a05' : '#93a8cd',
                  }}
                />
              </div>
              <div className="text-[9px] uppercase tracking-wide text-navy-400 mt-0.5 truncate">
                {k.replace('position_', 'pos ')}
              </div>
            </div>
          ))}
        </div>
      ) : null}

      <div className="mt-2 flex items-center justify-between text-2xs text-navy-400">
        <span className="inline-flex items-center gap-1">
          <Clock size={10} /> last update {seconds(f.t, 1)} sim-time
        </span>
        <span>
          anomalies <b className="text-navy-700">{summary?.anomalies ?? 0}</b> · events{' '}
          <b className="text-navy-700">{anomalies?.length ?? 0}</b>
        </span>
      </div>
    </Panel>
  )
}
