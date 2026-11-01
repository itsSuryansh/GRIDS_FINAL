import React from 'react'
import { Satellite, ShieldAlert, ShieldCheck, ShieldX, Clock } from 'lucide-react'
import Panel from './Panel'
import { STATUS_STYLES, fixed } from '../utils/format'

function Row({ label, value, tone = '' }) {
  return (
    <div className="flex items-baseline justify-between gap-2 py-[4.5px] border-b border-slate-100/90 last:border-0">
      <span className="metric-label">{label}</span>
      <span className={`text-[12px] font-mono tabular-nums tracking-tight ${tone || 'text-slate-900'} text-right`}>
        {value}
      </span>
    </div>
  )
}

const SHIELD = {
  healthy: { icon: ShieldCheck, cls: 'text-emerald-600' },
  degraded: { icon: ShieldAlert, cls: 'text-amber-600' },
  suspicious: { icon: ShieldX, cls: 'text-red-600' },
  unavailable: { icon: Satellite, cls: 'text-slate-400' },
}

/** Big, glanceable integrity verdict for the current fix. */
function Verdict({ status, anomaly, reason, score }) {
  const map = {
    healthy: { tone: 'emerald', label: 'Nominal', sub: 'fixes accepted, residuals in family' },
    degraded: { tone: 'amber', label: 'Degraded', sub: 'residuals above the clean-fix floor' },
    suspicious: { tone: 'red', label: 'Suspicious', sub: 'fixes rejected, inertial coasting' },
    unavailable: { tone: 'slate', label: 'No fix', sub: 'inertial prediction only' },
  }[status] || { tone: 'slate', label: 'Unknown', sub: '' }
  const tone = map.tone
  const ring = {
    emerald: 'border-emerald-200 bg-gradient-to-br from-emerald-50 to-white',
    amber: 'border-amber-200 bg-gradient-to-br from-amber-50 to-white',
    red: 'border-red-200 bg-gradient-to-br from-red-50 to-white',
    slate: 'border-slate-200 bg-gradient-to-br from-slate-50 to-white',
  }[tone]
  const text = {
    emerald: 'text-emerald-800', amber: 'text-amber-800', red: 'text-red-800', slate: 'text-slate-700',
  }[tone]
  return (
    <div className={`rounded-lg border px-2.5 py-2 ${ring}`}>
      <div className="flex items-center justify-between">
        <span className={`text-[13px] font-bold tracking-tight ${text}`}>{map.label}</span>
        <span className={`font-mono text-[11px] ${text} opacity-80`}>
          score {((score ?? 0) * 100).toFixed(0)}%
        </span>
      </div>
      <div className="text-[10px] text-slate-500 leading-snug mt-0.5">{map.sub}</div>
      {reason ? (
        <div className="mt-1.5 pt-1.5 border-t border-white/70 text-[10px] leading-snug text-slate-600">
          <span className="font-semibold uppercase tracking-[0.08em] text-[9px] text-slate-400 mr-1">
            {anomaly ? 'alert' : 'detector'}
          </span>
          {reason}
        </div>
      ) : null}
    </div>
  )
}

export default function GnssStatusPanel({ frame, summary, anomalies }) {
  const f = frame || {}
  const st = f.gnss_status || 'unavailable'
  const ShieldIcon = (SHIELD[st] || SHIELD.unavailable).icon

  return (
    <Panel
      title="GNSS integrity"
      icon={Satellite}
      tone={f.anomaly ? 'alert' : st === 'healthy' ? 'good' : st === 'unavailable' ? 'default' : 'warn'}
      actions={
        <span className={`chip ${STATUS_STYLES[st] || STATUS_STYLES.unavailable}`}>
          <ShieldIcon size={9.5} strokeWidth={2.6} />{st}
        </span>
      }
    >
      <Verdict status={st} anomaly={f.anomaly} reason={f.anomaly_reason} score={f.anomaly_score} />

      <div className="grid grid-cols-2 gap-x-3 mt-2">
        <Row label="Fix valid" value={f.gnss_available ? 'yes' : 'no'} tone={f.gnss_available ? 'text-emerald-700' : 'text-amber-700'} />
        <Row label="Accepted" value={f.gnss_accepted ? 'yes' : 'no'} tone={f.gnss_accepted ? '' : 'text-amber-700'} />
        <Row label="Residual" value={f.gnss_residual_m != null ? `${f.gnss_residual_m.toFixed(1)} m` : '—'} />
        <Row label="NIS" value={f.nis != null ? f.nis.toFixed(1) : '—'} />
        <Row label="Raw error" value={f.gnss_error_m != null ? `${f.gnss_error_m.toFixed(1)} m` : '—'} />
        <Row label="Rejected" value={f.rejected_count ?? 0} tone={f.rejected_count > 0 ? 'text-red-700' : ''} />
      </div>

      {f.anomaly_severities && Object.keys(f.anomaly_severities).length > 0 && (
        <div className="mt-2.5 grid grid-cols-5 gap-1.5">
          {Object.entries(f.anomaly_severities).map(([k, v]) => (
            <div key={k} title={`${k}: ${(v * 100).toFixed(0)}%`}>
              <div className="h-[5px] rounded-full bg-slate-100 overflow-hidden">
                <div
                  className="h-full rounded-full transition-all duration-300"
                  style={{
                    width: `${Math.min(100, v * 100)}%`,
                    background: v > 0.85 ? '#dc2626' : v > 0.45 ? '#d97706' : '#94a3b8',
                  }}
                />
              </div>
              <div className="text-[8px] uppercase tracking-[0.06em] text-slate-400 mt-1 truncate">
                {k.replace('position_', 'pos ')}
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="mt-2 pt-1.5 border-t border-slate-100 flex items-center justify-between text-[9.5px] text-slate-400">
        <span className="inline-flex items-center gap-1 font-mono"><Clock size={9} /> t = {fixed(f.t, 1)} s</span>
        <span>
          events <b className="text-slate-600">{anomalies?.length ?? 0}</b>
          <span className="mx-1 text-slate-300">·</span>
          frames <b className="text-slate-600">{summary?.samples ?? 0}</b>
        </span>
      </div>
    </Panel>
  )
}
