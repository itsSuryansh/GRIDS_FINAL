import React, { useCallback, useEffect, useMemo, useState } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  LineChart, Line, Legend, Cell, ReferenceArea,
} from 'recharts'
import {
  BarChart3, RefreshCw, Database, TriangleAlert, CheckCircle2, History,
  TrendingDown, MapPinned, Waves, Info,
} from 'lucide-react'
import api from '../services/api'
import BatchPanel from './BatchPanel'
import { COLORS, ALGO_META, fixed } from '../utils/format'

function Stat({ label, value, unit, tone = '', hint }) {
  return (
    <div className="px-3.5 py-2.5 border-r border-b border-slate-200/70">
      <div className="metric-label">{label}</div>
      <div className={`metric-value text-[15px] mt-[3px] ${tone}`}>
        {value}
        {unit ? <span className="text-[10px] text-slate-400 ml-1 font-sans">{unit}</span> : null}
      </div>
      {hint ? <div className="text-[10px] text-slate-400 mt-[2px] leading-snug">{hint}</div> : null}
    </div>
  )
}

function deltaTone(v, goodWhenPositive = true) {
  if (v == null) return ''
  if (goodWhenPositive) return v > 0.01 ? 'text-emerald-700' : v < -0.01 ? 'text-red-700' : ''
  return ''
}

function MetricsTable({ report, best }) {
  const algos = Object.keys(report.algorithms)
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-[9px] uppercase tracking-[0.1em] text-slate-400 border-b border-slate-200 bg-slate-50/80">
            <th className="text-left font-semibold px-3 py-2">Estimator</th>
            <th className="text-right font-semibold px-2 py-2">RMSE</th>
            <th className="text-right font-semibold px-2 py-2">MAE</th>
            <th className="text-right font-semibold px-2 py-2">Mean</th>
            <th className="text-right font-semibold px-2 py-2">P95</th>
            <th className="text-right font-semibold px-2 py-2">Max</th>
            <th className="text-right font-semibold px-3 py-2">Samples</th>
          </tr>
        </thead>
        <tbody>
          {algos.map((a) => {
            const m = report.algorithms[a]
            const meta = ALGO_META[a] || { label: a, color: COLORS.grid }
            const off = m.samples === 0
            return (
              <tr key={a} className={`border-b border-slate-100 last:border-0 transition-colors hover:bg-slate-50/70 ${off ? 'opacity-45' : ''} ${a === best ? 'bg-emerald-50/50' : ''}`}>
                <td className="px-3 py-2">
                  <span className="inline-flex items-center gap-1.5">
                    <span className="inline-block h-[7px] w-[7px] rounded-[2px] ring-1 ring-inset ring-black/5" style={{ background: meta.color }} />
                    <span className={`${a === best ? 'font-semibold text-slate-900' : 'font-medium text-slate-700'}`}>{meta.label}</span>
                    {a === best ? <span className="chip bg-emerald-100 text-emerald-800 border border-emerald-200">best</span> : null}
                    {off ? <span className="chip bg-slate-100 text-slate-500 border border-slate-200">n/a</span> : null}
                  </span>
                </td>
                <td className="px-2 py-2 text-right font-mono tabular-nums font-semibold text-slate-900">{fixed(m.rmse_m, 2)}</td>
                <td className="px-2 py-2 text-right font-mono tabular-nums">{fixed(m.mae_m, 2)}</td>
                <td className="px-2 py-2 text-right font-mono tabular-nums">{fixed(m.mean_m, 2)}</td>
                <td className="px-2 py-2 text-right font-mono tabular-nums">{fixed(m.p95_m, 2)}</td>
                <td className="px-2 py-2 text-right font-mono tabular-nums">{fixed(m.max_m, 2)}</td>
                <td className="px-3 py-2 text-right font-mono tabular-nums text-slate-500">{m.samples}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function bestAlgo(report) {
  const entries = Object.entries(report.algorithms).filter(([, m]) => m.samples > 0)
  if (!entries.length) return null
  return entries.reduce((a, b) => (a[1].rmse_m <= b[1].rmse_m ? a : b))[0]
}

export default function AnalyticsPage({ liveReport }) {
  const [report, setReport] = useState(liveReport || null)
  const [sessions, setSessions] = useState([])
  const [ml, setMl] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [source, setSource] = useState('live')

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [sess, mlInfo] = await Promise.all([api.sessions(), api.mlStatus()])
      setSessions(sess.sessions || [])
      setMl(mlInfo)
      try {
        const cmp = await api.compare(true)
        setReport(cmp)
        setSource('live')
      } catch {
        /* no live run; keep whatever is displayed */
      }
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    if (liveReport) {
      setReport((r) => (r?.run_id === liveReport.run_id ? r : liveReport))
      setSource('live')
    }
  }, [liveReport])

  const openSession = async (id) => {
    setError(null)
    try {
      const data = await api.session(id)
      const metrics = {}
      Object.entries(data.metrics || {}).forEach(([k, v]) => {
        metrics[k] = {
          rmse_m: v.rmse_m, mae_m: v.mae_m, max_m: v.max_m, p95_m: v.p95_m,
          mean_m: v.mean_m ?? 0, samples: v.samples,
        }
      })
      setReport({
        session_id: id,
        scenario: data.session.scenario,
        algorithms: metrics,
        anomalies: { detected: data.anomalies?.length ?? 0, rejected_measurements: data.session.rejected ?? undefined },
        deltas: {},
        notes: ['Loaded from the SQLite archive — batched navigation results, streamed back through the API.'],
        series: (data.series || []).map((s) => ({
          t: s.t, ekf_error_m: s.ekf_error_m, dr_error_m: s.dr_error_m,
          gnss_error_m: s.gnss_error_m, sm_error_m: s.sm_error_m, nomap_error_m: s.nomap_error_m,
        })),
      })
      setSource(`session #${id}`)
    } catch (e) {
      setError(e.message)
    }
  }

  const barData = useMemo(() => {
    if (!report) return []
    return Object.entries(report.algorithms)
      .filter(([, m]) => m.samples > 0)
      .map(([k, m]) => ({ name: ALGO_META[k]?.short || k, rmse: m.rmse_m, p95: m.p95_m, key: k }))
  }, [report])

  const best = report ? bestAlgo(report) : null
  const d = report?.deltas || {}
  const mlDelta = d.ml_vs_ekf_rmse_m

  return (
    <div className="p-3 space-y-3 overflow-y-auto h-full">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-[17px] font-bold tracking-[-0.01em] text-slate-900">Performance analytics</h1>
          <p className="text-[11px] text-slate-500 leading-snug">
            Six estimators scored at identical timestamps against one simulated ground-truth reference
            {report ? <span className="font-mono text-[10px] text-slate-400 ml-1">· source: {source}</span> : null}
          </p>
        </div>
        <button className="btn-secondary" onClick={load} disabled={loading}>
          <RefreshCw size={12} className={loading ? 'animate-spin' : ''} /> Refresh
        </button>
      </div>

      {error ? (
        <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">{error}</div>
      ) : null}

      {!report ? (
        <div className="panel px-4 py-8 text-center text-xs text-slate-500">
          No analytics yet — run a simulation, or open a stored session below.
        </div>
      ) : (
        <>
          <div className="panel">
            <div className="panel-header">
              <div className="flex items-center gap-2">
                <BarChart3 size={14} className="text-slate-400" />
                <h2 className="panel-title">
                  Algorithm comparison · {report.scenario}
                  {report.session_id ? ` · session #${report.session_id}` : ''}
                </h2>
              </div>
              <span className="text-3xs text-slate-400">{report.ground_truth_samples} ground-truth samples</span>
            </div>
            <MetricsTable report={report} best={best} />
            <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 border-t border-slate-200">
              <Stat label="Anomalies" value={report.anomalies?.detected ?? 0} />
              <Stat label="Rejected fixes" value={report.anomalies?.rejected_measurements ?? 0} />
              <Stat label="EKF vs raw GNSS" value={fixed(d.ekf_vs_gnss_rmse_m, 2)} unit="m" tone={deltaTone(d.ekf_vs_gnss_rmse_m)} hint="RMSE improvement" />
              <Stat label="Map aiding gain" value={d.map_vs_nomap_rmse_m != null ? fixed(d.map_vs_nomap_rmse_m, 2) : '—'} unit={d.map_vs_nomap_rmse_m != null ? 'm' : ''} tone={deltaTone(d.map_vs_nomap_rmse_m)} hint="EKF vs no-map shadow filter" />
              <Stat label="RTS smoothing gain" value={d.smoothing_vs_ekf_rmse_m != null ? fixed(d.smoothing_vs_ekf_rmse_m, 2) : '—'} unit={d.smoothing_vs_ekf_rmse_m != null ? 'm' : ''} tone={deltaTone(d.smoothing_vs_ekf_rmse_m)} hint="post-processed backward pass" />
              <Stat label="ML vs EKF" value={mlDelta != null ? fixed(mlDelta, 2) : 'not enabled'} unit={mlDelta != null ? 'm' : ''} tone={deltaTone(mlDelta)} hint="held-out evaluation" />
            </div>
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
            <div className="panel">
              <div className="panel-header"><h2 className="panel-title">RMSE vs P95 by estimator</h2></div>
              <div className="h-[248px] p-2">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={barData} margin={{ top: 6, right: 10, left: 0, bottom: 2 }}>
                    <CartesianGrid stroke="rgba(148,163,184,0.22)" strokeDasharray="2 4" vertical={false} />
                    <XAxis dataKey="name" tick={{ fontSize: 9.5, fill: '#64748b', fontFamily: 'JetBrains Mono Variable, monospace' }} tickLine={false} tickMargin={4} axisLine={{ stroke: 'rgba(148,163,184,0.35)' }} />
                    <YAxis tick={{ fontSize: 9, fill: '#94a3b8', fontFamily: 'JetBrains Mono Variable, monospace' }} tickLine={false} axisLine={false} width={44} tickMargin={4} unit="m" />
                    <Tooltip formatter={(v) => `${Number(v).toFixed(2)} m`} contentStyle={{ fontSize: 11, borderRadius: 8, borderColor: '#e2e8f0', boxShadow: '0 10px 30px -12px rgba(15,23,42,0.28)' }} />
                    <Legend wrapperStyle={{ fontSize: 10, paddingTop: 4 }} iconSize={8} iconType="plainline" />
                    <Bar dataKey="rmse" name="RMSE" radius={[3, 3, 0, 0]}>
                      {barData.map((b) => (<Cell key={b.key} fill={ALGO_META[b.key]?.color || '#94a3b8'} />))}
                    </Bar>
                    <Bar dataKey="p95" name="P95" fill="#e2e8f0" radius={[3, 3, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="panel">
              <div className="panel-header"><h2 className="panel-title">Error over time (same timestamps)</h2></div>
              <div className="h-[248px] p-2">
                {report.series?.length ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={report.series} margin={{ top: 6, right: 14, left: 0, bottom: 2 }}>
                      <CartesianGrid stroke="rgba(148,163,184,0.22)" strokeDasharray="2 4" vertical={false} />
                      <XAxis dataKey="t" tick={{ fontSize: 9, fill: '#94a3b8', fontFamily: 'JetBrains Mono Variable, monospace' }} tickLine={false} tickMargin={4} unit="s" minTickGap={34} axisLine={{ stroke: 'rgba(148,163,184,0.35)' }} />
                      <YAxis tick={{ fontSize: 9, fill: '#94a3b8', fontFamily: 'JetBrains Mono Variable, monospace' }} tickLine={false} axisLine={false} width={44} tickMargin={4} unit="m" />
                      <Tooltip contentStyle={{ fontSize: 11, borderRadius: 8, borderColor: '#e2e8f0', boxShadow: '0 10px 30px -12px rgba(15,23,42,0.28)' }} />
                      <Legend wrapperStyle={{ fontSize: 10, paddingTop: 4 }} iconSize={8} iconType="plainline" />
                      <Line type="monotone" dataKey="ekf_error_m" name="EKF" stroke={COLORS.ekf} dot={false} strokeWidth={1.7} isAnimationActive={false} />
                      <Line type="monotone" dataKey="sm_error_m" name="RTS" stroke={COLORS.smoothed} dot={false} strokeWidth={1.3} isAnimationActive={false} connectNulls />
                      <Line type="monotone" dataKey="dr_error_m" name="DR" stroke={COLORS.dr} dot={false} strokeWidth={1.1} isAnimationActive={false} />
                      <Line type="monotone" dataKey="gnss_error_m" name="GNSS" stroke={COLORS.gnss} dot={false} strokeWidth={1} strokeDasharray="4 2" isAnimationActive={false} />
                    </LineChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="h-full flex items-center justify-center text-xs text-slate-400">No time series stored for this session.</div>
                )}
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-3 gap-3">
            <div className="panel xl:col-span-2">
              <div className="panel-header">
                <div className="flex items-center gap-2"><Waves size={13} className="text-slate-400" /><h2 className="panel-title">Outage recovery</h2></div>
              </div>
              <div className="p-3 text-xs text-slate-600">
                {report.recovery && Object.keys(report.recovery).length ? (
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-0 border border-slate-200 rounded-md overflow-hidden">
                    <Stat label="Outage window" value={`${fixed(report.recovery.outage_start_s, 0)} – ${fixed(report.recovery.outage_end_s, 0)}`} unit="s" />
                    <Stat label="Peak error in outage" value={fixed(report.recovery.peak_error_during_outage_m, 2)} unit="m" />
                    <Stat label="Error at outage end" value={fixed(report.recovery.error_at_outage_end_m, 2)} unit="m" />
                    <Stat label="Drift rate in outage" value={fixed(report.recovery.drift_rate_during_outage_ms, 3)} unit="m/s" />
                    <Stat label="Recovery time" value={report.recovery.recovery_time_s != null ? fixed(report.recovery.recovery_time_s, 1) : 'not reached'} unit={report.recovery.recovery_time_s != null ? 's' : ''} />
                    <Stat label="Threshold" value={fixed(report.recovery.recovery_threshold_m, 0)} unit="m" />
                  </div>
                ) : (
                  <p className="text-slate-500">No GNSS outage in this run, so recovery metrics do not apply.</p>
                )}
                <ul className="mt-3 space-y-1.5 text-[10.5px] text-slate-500 leading-[1.5]">
                  {(report.notes || []).map((n, i) => (
                    <li key={i} className="relative pl-2.5 before:absolute before:left-0 before:top-[5px] before:h-[3px] before:w-[3px] before:rounded-full before:bg-slate-300">
                      {n}
                    </li>
                  ))}
                </ul>
              </div>
            </div>

            <div className="panel">
              <div className="panel-header">
                <div className="flex items-center gap-2"><Info size={13} className="text-slate-400" /><h2 className="panel-title">ML correction layer</h2></div>
              </div>
              <div className="p-3 text-xs text-slate-600 space-y-1.5">
                <div className="flex items-center gap-1.5">
                  {ml?.available ? <CheckCircle2 size={13} className="text-emerald-600" /> : <TriangleAlert size={13} className="text-amber-600" />}
                  <span className="font-medium">{ml?.available ? 'Trained model available' : 'No trained model'}</span>
                </div>
                {ml?.evaluation?.baseline_ekf ? (
                  <>
                    <div className="mt-1 rounded-md border border-slate-200 overflow-hidden">
                      {[
                        ['Baseline EKF RMSE', fixed(ml.evaluation.baseline_ekf.rmse_m, 2), ''],
                        ['With ML correction', fixed(ml.evaluation.corrected.rmse_m, 2), ''],
                        [
                          'Difference',
                          fixed(ml.evaluation.rmse_improvement_m, 2),
                          ml.evaluation.rmse_improvement_m > 0 ? 'text-emerald-700' : 'text-red-700',
                        ],
                      ].map(([label, val, tone]) => (
                        <div
                          key={label}
                          className="flex items-baseline justify-between gap-3 px-2 py-[5px] border-b border-slate-100 last:border-0 bg-slate-50/50"
                        >
                          <span className="text-[10px] text-slate-500">{label}</span>
                          <span className={`text-[11px] font-mono tabular-nums ${tone || 'text-slate-800'}`}>{val} m</span>
                        </div>
                      ))}
                    </div>
                    <p className="text-[10px] text-slate-500 leading-[1.5]">
                      Held-out: {ml.evaluation.test_samples} samples / {ml.evaluation.test_sessions} unseen
                      sessions.{' '}
                      {ml.evaluation.recommended_default
                        ? 'Measured improvement — safe to enable.'
                        : 'No measured improvement, so the layer stays disabled by default.'}
                    </p>
                  </>
                ) : (
                  <p className="text-[10.5px] text-slate-500 leading-[1.5]">
                    Train with <code className="font-mono bg-slate-100 rounded px-1 py-0.5 text-[10px]">python -m app.ml.train</code>{' '}
                    to produce a measured comparison on held-out simulated sessions.
                  </p>
                )}
              </div>
            </div>
          </div>
        </>
      )}

      <BatchPanel />

      <div className="panel">
        <div className="panel-header">
          <div className="flex items-center gap-2"><Database size={14} className="text-slate-400" /><h2 className="panel-title">Stored sessions</h2></div>
          <span className="text-[9.5px] font-mono tabular-nums text-slate-400">{sessions.length} in SQLite</span>
        </div>
        {sessions.length === 0 ? (
          <div className="px-3 py-4 text-xs text-slate-500">No sessions stored yet. Start and stop a simulation to archive one.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-[9px] uppercase tracking-[0.1em] text-slate-400 border-b border-slate-200 bg-slate-50/80">
                  <th className="text-left px-3 py-2 font-semibold">#</th>
                  <th className="text-left px-2 py-2 font-semibold">Scenario</th>
                  <th className="text-left px-2 py-2 font-semibold">Route</th>
                  <th className="text-right px-2 py-2 font-semibold">Duration</th>
                  <th className="text-right px-2 py-2 font-semibold">EKF</th>
                  <th className="text-right px-2 py-2 font-semibold">RTS</th>
                  <th className="text-right px-2 py-2 font-semibold">DR</th>
                  <th className="text-right px-2 py-2 font-semibold">GNSS</th>
                  <th className="text-left px-3 py-2 font-semibold">Status</th>
                </tr>
              </thead>
              <tbody>
                {sessions.map((s) => (
                  <tr key={s.id} onClick={() => openSession(s.id)} className="border-b border-slate-100 last:border-0 hover:bg-blue-50/50 cursor-pointer transition-colors" title="Open this session's report">
                    <td className="px-3 py-2 font-mono text-slate-400">{s.id}</td>
                    <td className="px-2 py-2 font-medium text-slate-800">{s.scenario}</td>
                    <td className="px-2 py-2 text-slate-600">{s.route_pattern}</td>
                    <td className="px-2 py-2 text-right font-mono">{fixed(s.duration_s, 1)} s</td>
                    <td className="px-2 py-2 text-right font-mono text-blue-800">{fixed(s.metrics?.ekf?.rmse_m, 2)}</td>
                    <td className="px-2 py-2 text-right font-mono text-teal-700">{fixed(s.metrics?.rts_smoothed?.rmse_m, 2)}</td>
                    <td className="px-2 py-2 text-right font-mono">{fixed(s.metrics?.dead_reckoning?.rmse_m, 2)}</td>
                    <td className="px-2 py-2 text-right font-mono">{fixed(s.metrics?.gnss?.rmse_m, 2)}</td>
                    <td className="px-3 py-2">
                      <span className={`chip border ${
                        s.status === 'completed'
                          ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                          : 'bg-slate-50 text-slate-600 border-slate-200'
                      }`}>{s.status}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="px-3 py-2 text-[9.5px] text-slate-400 border-t border-slate-200 flex items-center gap-1.5">
          <History size={10} /> High-frequency frames are batched before being written, so storage stays compact.
        </div>
      </div>
    </div>
  )
}
