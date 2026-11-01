import React, { useCallback, useEffect, useMemo, useState } from 'react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  LineChart,
  Line,
  Legend,
  Cell,
} from 'recharts'
import { BarChart3, RefreshCw, Database, TriangleAlert, CheckCircle2, History } from 'lucide-react'
import api from '../services/api'
import { COLORS, fixed } from '../utils/format'

const ALGO_LABEL = {
  gnss: 'GNSS (raw)',
  dead_reckoning: 'Dead reckoning',
  ekf: 'EKF fusion',
  ekf_ml: 'EKF + ML',
}
const ALGO_COLOR = {
  gnss: COLORS.gnss,
  dead_reckoning: COLORS.dr,
  ekf: COLORS.ekf,
  ekf_ml: COLORS.ml,
}

function Stat({ label, value, unit, tone = '' }) {
  return (
    <div className="px-3 py-2 border-r border-b border-navy-100">
      <div className="metric-label">{label}</div>
      <div className={`metric-value text-sm ${tone}`}>
        {value}
        {unit ? <span className="text-2xs text-navy-400 ml-1 font-sans">{unit}</span> : null}
      </div>
    </div>
  )
}

function MetricsTable({ report }) {
  const algos = Object.keys(report.algorithms)
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-2xs uppercase tracking-wider text-navy-400 border-b border-navy-100">
            <th className="text-left font-semibold px-3 py-1.5">Estimator</th>
            <th className="text-right font-semibold px-2 py-1.5">RMSE (m)</th>
            <th className="text-right font-semibold px-2 py-1.5">MAE (m)</th>
            <th className="text-right font-semibold px-2 py-1.5">Mean (m)</th>
            <th className="text-right font-semibold px-2 py-1.5">P95 (m)</th>
            <th className="text-right font-semibold px-2 py-1.5">Max (m)</th>
            <th className="text-right font-semibold px-3 py-1.5">Samples</th>
          </tr>
        </thead>
        <tbody>
          {algos.map((a) => {
            const m = report.algorithms[a]
            const best = a === bestAlgo(report)
            const disabled = m.samples === 0
            return (
              <tr key={a} className={`border-b border-navy-50 ${disabled ? 'opacity-50' : ''}`}>
                <td className="px-3 py-1.5">
                  <span className="inline-flex items-center gap-1.5">
                    <span className="inline-block h-2 w-2 rounded-sm" style={{ background: ALGO_COLOR[a] }} />
                    <span className="font-medium text-navy-800">{ALGO_LABEL[a]}</span>
                    {best ? (
                      <span className="chip bg-emerald-50 text-emerald-700 border border-emerald-200">best</span>
                    ) : null}
                  </span>
                </td>
                <td className="px-2 py-1.5 text-right font-mono tabular-nums">{fixed(m.rmse_m, 2)}</td>
                <td className="px-2 py-1.5 text-right font-mono tabular-nums">{fixed(m.mae_m, 2)}</td>
                <td className="px-2 py-1.5 text-right font-mono tabular-nums">{fixed(m.mean_m, 2)}</td>
                <td className="px-2 py-1.5 text-right font-mono tabular-nums">{fixed(m.p95_m, 2)}</td>
                <td className="px-2 py-1.5 text-right font-mono tabular-nums">{fixed(m.max_m, 2)}</td>
                <td className="px-3 py-1.5 text-right font-mono tabular-nums text-navy-500">{m.samples}</td>
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

export default function AnalyticsPage({ liveReport, frame }) {
  const [report, setReport] = useState(liveReport || null)
  const [sessions, setSessions] = useState([])
  const [selected, setSelected] = useState(null)
  const [ml, setMl] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

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
      } catch {
        /* no live run: keep the stored report if any */
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
    if (liveReport) setReport((r) => (r?.run_id === liveReport.run_id ? r : liveReport))
  }, [liveReport])

  const openSession = async (id) => {
    try {
      const data = await api.session(id)
      setSelected(data)
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
        anomalies: { detected: data.anomalies?.length ?? 0 },
        notes: ['Loaded from the SQLite archive (batched navigation results).'],
        series: (data.series || []).map((s) => ({
          t: s.t, ekf_error_m: s.ekf_error_m, dr_error_m: s.dr_error_m,
          gnss_error_m: s.gnss_error_m, uncertainty_m: null, drift_m: null,
        })),
      })
    } catch (e) {
      setError(e.message)
    }
  }

  const barData = useMemo(() => {
    if (!report) return []
    return Object.entries(report.algorithms)
      .filter(([, m]) => m.samples > 0)
      .map(([k, m]) => ({ name: ALGO_LABEL[k], rmse: m.rmse_m, p95: m.p95_m, key: k }))
  }, [report])

  const mlDelta = report?.deltas?.ml_vs_ekf_rmse_m

  return (
    <div className="p-3 space-y-3 overflow-y-auto h-full">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-sm font-bold text-navy-900">Performance analytics</h1>
          <p className="text-2xs text-navy-500">
            Every estimator scored against the same simulated ground-truth reference at identical
            timestamps.
          </p>
        </div>
        <button className="btn-secondary" onClick={load} disabled={loading}>
          <RefreshCw size={12} className={loading ? 'animate-spin' : ''} /> Refresh
        </button>
      </div>

      {error ? (
        <div className="rounded border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">{error}</div>
      ) : null}

      {!report ? (
        <div className="panel px-4 py-6 text-center text-xs text-navy-500">
          No analytics yet — run a simulation, or open a stored session below.
        </div>
      ) : (
        <>
          <div className="panel">
            <div className="panel-header">
              <div className="flex items-center gap-2">
                <BarChart3 size={14} className="text-navy-400" />
                <h2 className="panel-title">
                  Algorithm comparison · {report.scenario}
                  {report.session_id ? ` · session #${report.session_id}` : ''}
                </h2>
              </div>
              <span className="text-2xs text-navy-400">
                {report.ground_truth_samples} ground-truth samples
              </span>
            </div>
            <MetricsTable report={report} />
            <div className="grid grid-cols-2 md:grid-cols-4 border-t border-navy-100">
              <Stat label="Anomalies detected" value={report.anomalies?.detected ?? 0} />
              <Stat label="Rejected fixes" value={report.anomalies?.rejected_measurements ?? 0} />
              <Stat
                label="EKF vs GNSS RMSE gain"
                value={report.deltas?.ekf_vs_gnss_rmse_m != null ? fixed(report.deltas.ekf_vs_gnss_rmse_m, 2) : '—'}
                unit="m"
                tone={report.deltas?.ekf_vs_gnss_rmse_m > 0 ? 'text-emerald-700' : 'text-navy-900'}
              />
              <Stat
                label="ML vs EKF RMSE gain"
                value={mlDelta != null ? fixed(mlDelta, 2) : 'not enabled'}
                unit={mlDelta != null ? 'm' : ''}
                tone={mlDelta > 0 ? 'text-emerald-700' : mlDelta < 0 ? 'text-red-700' : ''}
              />
            </div>
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
            <div className="panel">
              <div className="panel-header">
                <h2 className="panel-title">RMSE vs P95 by estimator</h2>
              </div>
              <div className="h-[240px] p-2">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={barData} margin={{ top: 6, right: 8, left: -18, bottom: 0 }}>
                    <CartesianGrid stroke={COLORS.grid} strokeDasharray="2 3" />
                    <XAxis dataKey="name" tick={{ fontSize: 9, fill: '#5d7cb1' }} tickLine={false} />
                    <YAxis tick={{ fontSize: 9, fill: '#5d7cb1' }} tickLine={false} axisLine={false} width={46} unit="m" />
                    <Tooltip
                      formatter={(v) => `${Number(v).toFixed(2)} m`}
                      contentStyle={{ fontSize: 11, borderRadius: 4, borderColor: '#c3cfe4' }}
                    />
                    <Legend wrapperStyle={{ fontSize: 10 }} />
                    <Bar dataKey="rmse" name="RMSE" radius={[2, 2, 0, 0]}>
                      {barData.map((d) => (
                        <Cell key={d.key} fill={ALGO_COLOR[d.key]} />
                      ))}
                    </Bar>
                    <Bar dataKey="p95" name="P95" fill="#c3cfe4" radius={[2, 2, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="panel">
              <div className="panel-header">
                <h2 className="panel-title">Error over time (same timestamps)</h2>
              </div>
              <div className="h-[240px] p-2">
                {report.series?.length ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={report.series} margin={{ top: 6, right: 8, left: -18, bottom: 0 }}>
                      <CartesianGrid stroke={COLORS.grid} strokeDasharray="2 3" />
                      <XAxis dataKey="t" tick={{ fontSize: 9, fill: '#5d7cb1' }} tickLine={false} unit="s" minTickGap={30} />
                      <YAxis tick={{ fontSize: 9, fill: '#5d7cb1' }} tickLine={false} axisLine={false} width={46} unit="m" />
                      <Tooltip contentStyle={{ fontSize: 11, borderRadius: 4, borderColor: '#c3cfe4' }} />
                      <Legend wrapperStyle={{ fontSize: 10 }} />
                      <Line type="monotone" dataKey="ekf_error_m" name="EKF" stroke={COLORS.ekf} dot={false} strokeWidth={1.6} isAnimationActive={false} />
                      <Line type="monotone" dataKey="dr_error_m" name="Dead reckoning" stroke={COLORS.dr} dot={false} strokeWidth={1.2} isAnimationActive={false} />
                      <Line type="monotone" dataKey="gnss_error_m" name="GNSS" stroke={COLORS.gnss} dot={false} strokeWidth={1.1} strokeDasharray="4 2" isAnimationActive={false} />
                      {report.series.some((s) => s.ml_error_m != null) && (
                        <Line type="monotone" dataKey="ml_error_m" name="EKF + ML" stroke={COLORS.ml} dot={false} strokeWidth={1.2} isAnimationActive={false} />
                      )}
                    </LineChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="h-full flex items-center justify-center text-xs text-navy-400">
                    No time series stored for this session.
                  </div>
                )}
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-3 gap-3">
            <div className="panel xl:col-span-2">
              <div className="panel-header">
                <h2 className="panel-title">Outage recovery</h2>
              </div>
              <div className="p-3 text-xs text-navy-600">
                {report.recovery && Object.keys(report.recovery).length ? (
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                    <Stat label="Outage window" value={`${fixed(report.recovery.outage_start_s, 0)} – ${fixed(report.recovery.outage_end_s, 0)}`} unit="s" />
                    <Stat label="Peak error in outage" value={fixed(report.recovery.peak_error_during_outage_m, 2)} unit="m" />
                    <Stat label="Error at outage end" value={fixed(report.recovery.error_at_outage_end_m, 2)} unit="m" />
                    <Stat label="Drift rate in outage" value={fixed(report.recovery.drift_rate_during_outage_ms, 3)} unit="m/s" />
                    <Stat
                      label="Recovery time"
                      value={report.recovery.recovery_time_s != null ? fixed(report.recovery.recovery_time_s, 1) : 'not reached'}
                      unit={report.recovery.recovery_time_s != null ? 's' : ''}
                    />
                    <Stat label="Recovery threshold" value={fixed(report.recovery.recovery_threshold_m, 0)} unit="m" />
                  </div>
                ) : (
                  <p className="text-navy-500">
                    No GNSS outage in this run, so recovery metrics do not apply.
                  </p>
                )}
                <ul className="mt-3 space-y-1 text-2xs text-navy-500 list-disc list-inside">
                  {(report.notes || []).map((n, i) => (
                    <li key={i}>{n}</li>
                  ))}
                </ul>
              </div>
            </div>

            <div className="panel">
              <div className="panel-header">
                <h2 className="panel-title">ML correction layer</h2>
              </div>
              <div className="p-3 text-xs text-navy-600 space-y-1.5">
                <div className="flex items-center gap-1.5">
                  {ml?.available ? (
                    <CheckCircle2 size={13} className="text-emerald-600" />
                  ) : (
                    <TriangleAlert size={13} className="text-amber-600" />
                  )}
                  <span className="font-medium">
                    {ml?.available ? 'Trained model available' : 'No trained model found'}
                  </span>
                </div>
                {ml?.evaluation?.baseline_ekf ? (
                  <>
                    <div className="font-mono text-2xs">
                      EKF baseline RMSE: {fixed(ml.evaluation.baseline_ekf.rmse_m, 2)} m
                      <br />
                      With correction: {fixed(ml.evaluation.corrected.rmse_m, 2)} m
                      <br />
                      Δ: {fixed(ml.evaluation.rmse_improvement_m, 2)} m
                    </div>
                    <div className="text-2xs text-navy-500">
                      Held-out: {ml.evaluation.test_samples} samples from{' '}
                      {ml.evaluation.test_sessions} unseen sessions.
                      {ml.evaluation.recommended_default
                        ? ' Measured improvement — safe to enable.'
                        : ' No measured improvement, so the layer stays disabled by default.'}
                    </div>
                  </>
                ) : (
                  <p className="text-2xs text-navy-500">
                    Train it with <code className="font-mono">python -m app.ml.train</code> to see a
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
          <div className="flex items-center gap-2">
            <Database size={14} className="text-navy-400" />
            <h2 className="panel-title">Stored sessions</h2>
          </div>
          <span className="text-2xs text-navy-400">{sessions.length} in SQLite</span>
        </div>
        {sessions.length === 0 ? (
          <div className="px-3 py-4 text-xs text-navy-500">
            No sessions stored yet. Start and stop a simulation to archive one.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-2xs uppercase tracking-wider text-navy-400 border-b border-navy-100">
                  <th className="text-left px-3 py-1.5 font-semibold">#</th>
                  <th className="text-left px-2 py-1.5 font-semibold">Scenario</th>
                  <th className="text-left px-2 py-1.5 font-semibold">Route</th>
                  <th className="text-right px-2 py-1.5 font-semibold">Duration</th>
                  <th className="text-right px-2 py-1.5 font-semibold">EKF RMSE</th>
                  <th className="text-right px-2 py-1.5 font-semibold">DR RMSE</th>
                  <th className="text-right px-2 py-1.5 font-semibold">GNSS RMSE</th>
                  <th className="text-left px-3 py-1.5 font-semibold">Status</th>
                </tr>
              </thead>
              <tbody>
                {sessions.map((s) => (
                  <tr
                    key={s.id}
                    onClick={() => openSession(s.id)}
                    className="border-b border-navy-50 hover:bg-navy-50 cursor-pointer"
                    title="Open this session's report"
                  >
                    <td className="px-3 py-1.5 font-mono text-navy-500">{s.id}</td>
                    <td className="px-2 py-1.5 font-medium text-navy-800">{s.scenario}</td>
                    <td className="px-2 py-1.5 text-navy-600">{s.route_pattern}</td>
                    <td className="px-2 py-1.5 text-right font-mono">{fixed(s.duration_s, 1)} s</td>
                    <td className="px-2 py-1.5 text-right font-mono">{fixed(s.metrics?.ekf?.rmse_m, 2)}</td>
                    <td className="px-2 py-1.5 text-right font-mono">{fixed(s.metrics?.dead_reckoning?.rmse_m, 2)}</td>
                    <td className="px-2 py-1.5 text-right font-mono">{fixed(s.metrics?.gnss?.rmse_m, 2)}</td>
                    <td className="px-3 py-1.5">
                      <span className="chip bg-navy-50 text-navy-600 border border-navy-200">{s.status}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="px-3 py-1.5 text-2xs text-navy-400 border-t border-navy-100 flex items-center gap-1">
          <History size={10} /> High-frequency frames are batched before being written, so storage stays
          compact.
        </div>
      </div>
    </div>
  )
}
