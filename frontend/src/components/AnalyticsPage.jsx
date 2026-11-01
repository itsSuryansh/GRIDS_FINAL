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
import { COLORS, ALGO_META, fixed } from '../utils/format'

function Stat({ label, value, unit, tone = '', hint }) {
  return (
    <div className="px-3 py-2 border-r border-b border-slate-200/70">
      <div className="metric-label">{label}</div>
      <div className={`metric-value text-[13px] ${tone}`}>
        {value}
        {unit ? <span className="text-3xs text-slate-400 ml-1 font-sans">{unit}</span> : null}
      </div>
      {hint ? <div className="text-3xs text-slate-400">{hint}</div> : null}
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
          <tr className="text-3xs uppercase tracking-wider text-slate-400 border-b border-slate-200 bg-slate-50/60">
            <th className="text-left font-semibold px-3 py-1.5">Estimator</th>
            <th className="text-right font-semibold px-2 py-1.5">RMSE</th>
            <th className="text-right font-semibold px-2 py-1.5">MAE</th>
            <th className="text-right font-semibold px-2 py-1.5">Mean</th>
            <th className="text-right font-semibold px-2 py-1.5">P95</th>
            <th className="text-right font-semibold px-2 py-1.5">Max</th>
            <th className="text-right font-semibold px-3 py-1.5">Samples</th>
          </tr>
        </thead>
        <tbody>
          {algos.map((a) => {
            const m = report.algorithms[a]
            const meta = ALGO_META[a] || { label: a, color: COLORS.grid }
            const off = m.samples === 0
            return (
              <tr key={a} className={`border-b border-slate-100 ${off ? 'opacity-45' : ''} ${a === best ? 'bg-emerald-50/40' : ''}`}>
                <td className="px-3 py-1.5">
                  <span className="inline-flex items-center gap-1.5">
                    <span className="inline-block h-2 w-2 rounded-sm" style={{ background: meta.color }} />
                    <span className={`${a === best ? 'font-semibold text-slate-900' : 'font-medium text-slate-700'}`}>{meta.label}</span>
                    {a === best ? <span className="chip bg-emerald-100 text-emerald-800 border border-emerald-200">best</span> : null}
                    {off ? <span className="chip bg-slate-100 text-slate-500 border border-slate-200">n/a</span> : null}
                  </span>
                </td>
                <td className="px-2 py-1.5 text-right font-mono tabular-nums">{fixed(m.rmse_m, 2)}</td>
                <td className="px-2 py-1.5 text-right font-mono tabular-nums">{fixed(m.mae_m, 2)}</td>
                <td className="px-2 py-1.5 text-right font-mono tabular-nums">{fixed(m.mean_m, 2)}</td>
                <td className="px-2 py-1.5 text-right font-mono tabular-nums">{fixed(m.p95_m, 2)}</td>
                <td className="px-2 py-1.5 text-right font-mono tabular-nums">{fixed(m.max_m, 2)}</td>
                <td className="px-3 py-1.5 text-right font-mono tabular-nums text-slate-500">{m.samples}</td>
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
          <h1 className="text-sm font-bold text-slate-900">Performance analytics</h1>
          <p className="text-2xs text-slate-500">
            Six estimators, identical timestamps, one simulated ground-truth reference.{' '}
            {report ? <span className="font-mono text-slate-600">source: {source}</span> : null}
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
                  <BarChart data={barData} margin={{ top: 6, right: 8, left: -18, bottom: 0 }}>
                    <CartesianGrid stroke={COLORS.grid} strokeDasharray="2 3" />
                    <XAxis dataKey="name" tick={{ fontSize: 9, fill: '#64748b' }} tickLine={false} />
                    <YAxis tick={{ fontSize: 9, fill: '#64748b' }} tickLine={false} axisLine={false} width={46} unit="m" />
                    <Tooltip formatter={(v) => `${Number(v).toFixed(2)} m`} contentStyle={{ fontSize: 11, borderRadius: 6, borderColor: '#cbd5e1' }} />
                    <Legend wrapperStyle={{ fontSize: 10 }} />
                    <Bar dataKey="rmse" name="RMSE" radius={[3, 3, 0, 0]}>
                      {barData.map((b) => (<Cell key={b.key} fill={ALGO_META[b.key]?.color || '#94a3b8'} />))}
                    </Bar>
                    <Bar dataKey="p95" name="P95" fill="#cbd5e1" radius={[3, 3, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="panel">
              <div className="panel-header"><h2 className="panel-title">Error over time (same timestamps)</h2></div>
              <div className="h-[248px] p-2">
                {report.series?.length ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={report.series} margin={{ top: 6, right: 10, left: -18, bottom: 0 }}>
                      <CartesianGrid stroke={COLORS.grid} strokeDasharray="2 3" />
                      <XAxis dataKey="t" tick={{ fontSize: 9, fill: '#64748b' }} tickLine={false} unit="s" minTickGap={30} />
                      <YAxis tick={{ fontSize: 9, fill: '#64748b' }} tickLine={false} axisLine={false} width={46} unit="m" />
                      <Tooltip contentStyle={{ fontSize: 11, borderRadius: 6, borderColor: '#cbd5e1' }} />
                      <Legend wrapperStyle={{ fontSize: 10 }} />
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
                <ul className="mt-3 space-y-1 text-2xs text-slate-500 list-disc list-inside">
                  {(report.notes || []).map((n, i) => (<li key={i}>{n}</li>))}
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
                    <div className="font-mono text-2xs">
                      baseline EKF RMSE {fixed(ml.evaluation.baseline_ekf.rmse_m, 2)} m
                      <br />
                      with correction {fixed(ml.evaluation.corrected.rmse_m, 2)} m
                      <br />
                      Δ {fixed(ml.evaluation.rmse_improvement_m, 2)} m
                    </div>
                    <p className="text-2xs text-slate-500">
                      Held-out: {ml.evaluation.test_samples} samples / {ml.evaluation.test_sessions} unseen
                      sessions.{' '}
                      {ml.evaluation.recommended_default
                        ? 'Measured improvement — safe to enable.'
                        : 'No measured improvement, so the layer stays disabled by default.'}
                    </p>
                  </>
                ) : (
                  <p className="text-2xs text-slate-500">
                    Train with <code className="font-mono">python -m app.ml.train</code> to produce a
                    measured comparison on held-out simulated sessions.
                  </p>
                )}
              </div>
            </div>
          </div>
        </>
      )}

      <div className="panel">
        <div className="panel-header">
          <div className="flex items-center gap-2"><Database size={14} className="text-slate-400" /><h2 className="panel-title">Stored sessions</h2></div>
          <span className="text-3xs text-slate-400">{sessions.length} in SQLite</span>
        </div>
        {sessions.length === 0 ? (
          <div className="px-3 py-4 text-xs text-slate-500">No sessions stored yet. Start and stop a simulation to archive one.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-3xs uppercase tracking-wider text-slate-400 border-b border-slate-200 bg-slate-50/60">
                  <th className="text-left px-3 py-1.5 font-semibold">#</th>
                  <th className="text-left px-2 py-1.5 font-semibold">Scenario</th>
                  <th className="text-left px-2 py-1.5 font-semibold">Route</th>
                  <th className="text-right px-2 py-1.5 font-semibold">Duration</th>
                  <th className="text-right px-2 py-1.5 font-semibold">EKF</th>
                  <th className="text-right px-2 py-1.5 font-semibold">RTS</th>
                  <th className="text-right px-2 py-1.5 font-semibold">DR</th>
                  <th className="text-right px-2 py-1.5 font-semibold">GNSS</th>
                  <th className="text-left px-3 py-1.5 font-semibold">Status</th>
                </tr>
              </thead>
              <tbody>
                {sessions.map((s) => (
                  <tr key={s.id} onClick={() => openSession(s.id)} className="border-b border-slate-100 hover:bg-blue-50/50 cursor-pointer" title="Open this session's report">
                    <td className="px-3 py-1.5 font-mono text-slate-500">{s.id}</td>
                    <td className="px-2 py-1.5 font-medium text-slate-800">{s.scenario}</td>
                    <td className="px-2 py-1.5 text-slate-600">{s.route_pattern}</td>
                    <td className="px-2 py-1.5 text-right font-mono">{fixed(s.duration_s, 1)} s</td>
                    <td className="px-2 py-1.5 text-right font-mono text-blue-800">{fixed(s.metrics?.ekf?.rmse_m, 2)}</td>
                    <td className="px-2 py-1.5 text-right font-mono text-teal-700">{fixed(s.metrics?.rts_smoothed?.rmse_m, 2)}</td>
                    <td className="px-2 py-1.5 text-right font-mono">{fixed(s.metrics?.dead_reckoning?.rmse_m, 2)}</td>
                    <td className="px-2 py-1.5 text-right font-mono">{fixed(s.metrics?.gnss?.rmse_m, 2)}</td>
                    <td className="px-3 py-1.5"><span className="chip bg-slate-50 text-slate-600 border border-slate-200">{s.status}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="px-3 py-1.5 text-3xs text-slate-400 border-t border-slate-200 flex items-center gap-1">
          <History size={10} /> High-frequency frames are batched before being written, so storage stays compact.
        </div>
      </div>
    </div>
  )
}
