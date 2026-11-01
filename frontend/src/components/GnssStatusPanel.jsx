import React from 'react'
import { Satellite, ShieldAlert, ShieldCheck, ShieldX, Clock } from 'lucide-react'
import Panel from './Panel'
import { STATUS_STYLES, fixed } from '../utils/format'

function Row({ label, value, tone = '' }) {
  return (
    <div className="flex items-baseline justify-between gap-2 py-[3px] border-b border-slate-100 last:border-0">
      <span className="metric-label">{label}</span>
      <span className={`text-xs font-mono tabular-nums ${tone || 'text-slate-900'} text-right`}>{value}</span>
    </div>
  )
}

const SHIELD = {
  healthy: { icon: ShieldCheck, cls: 'text-emerald-600' },
  degraded: { icon: ShieldAlert, cls: 'text-amber-600' },
  suspicious: { icon: ShieldX, cls: 'text-red-600' },
  unavailable: { icon: Satellite, cls: 'text-slate-400' },
}

export default function GnssStatusPanel({ frame, summary, anomalies }) {
  const f = frame || {}
  const st = f.gnss_status || 'unavailable'
  const shield = SHIELD[st] || SHIELD.unavailable
  const ShieldIcon = shield.icon

  return (
    <Panel
      title="GNSS integrity"
      icon={Satellite}
      actions={<span className={`chip ${STATUS_STYLES[st] || STATUS_STYLES.unavailable}`}><ShieldIcon size={10} />{st}</span>}
    >
      <div className="grid grid-cols-2 gap-x-3">
        <Row label="Fix valid" value={f.gnss_available ? 'yes' : 'no'} tone={f.gnss_available ? 'text-emerald-700' : 'text-amber-700'} />
        <Row label="Accepted" value={f.gnss_accepted ? 'yes' : 'no'} tone={f.gnss_accepted ? '' : 'text-amber-700'} />
        <Row label="Residual" value={f.gnss_residual_m != null ? `${f.gnss_residual_m.toFixed(1)} m` : '—'} />
        <Row label="NIS" value={f.nis != null ? f.nis.toFixed(1) : '—'} />
        <Row label="Anomaly score" value={f.anomaly_score != null ? `${(f.anomaly_score * 100).toFixed(0)} %` : '—'} tone={f.anomaly ? 'text-red-700' : ''} />
        <Row label="Raw error" value={f.gnss_error_m != null ? `${f.gnss_error_m.toFixed(1)} m` : '—'} />
        <Row label="Rejected" value={f.rejected_count ?? 0} tone={f.rejected_count > 0 ? 'text-red-700' : ''} />
        <Row label="Detector" value={f.anomaly ? 'alert' : 'nominal'} tone={f.anomaly ? 'text-red-700' : 'text-emerald-700'} />
      </div>

      {f.anomaly_reason && (
        <div className={`mt-2 rounded-md border px-2 py-1.5 text-3xs leading-snug ${f.anomaly ? 'border-red-200 bg-red-50 text-red-800' : 'border-slate-200 bg-slate-50 text-slate-600'}`}>
          <span className="font-bold uppercase tracking-wider mr-1">{f.anomaly ? f.anomaly_type : 'detector'}</span>
          {f.anomaly_reason}
        </div>
      )}

      {f.anomaly_severities && Object.keys(f.anomaly_severities).length > 0 && (
        <div className="mt-2 grid grid-cols-5 gap-1.5">
          {Object.entries(f.anomaly_severities).map(([k, v]) => (
            <div key={k} title={`${k}: ${(v * 100).toFixed(0)}%`}>
              <div className="h-1.5 rounded-full bg-slate-100 overflow-hidden">
                <div
                  className="h-full rounded-full transition-all duration-200"
                  style={{
                    width: `${Math.min(100, v * 100)}%`,
                    background: v > 0.85 ? '#dc2626' : v > 0.45 ? '#d97706' : '#94a3b8',
                  }}
                />
              </div>
              <div className="text-[8.5px] uppercase tracking-wide text-slate-400 mt-0.5 truncate">
                {k.replace('position_', 'pos ')}
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="mt-2 flex items-center justify-between text-3xs text-slate-400">
        <span className="inline-flex items-center gap-1"><Clock size={9} /> t = {fixed(f.t, 1)} s</span>
        <span>events <b className="text-slate-700">{anomalies?.length ?? 0}</b> · frames {summary?.samples ?? 0}</span>
      </div>
    </Panel>
  )
}
