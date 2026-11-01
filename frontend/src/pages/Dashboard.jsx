import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { LayoutDashboard, BarChart3, X, Radio, TriangleAlert } from 'lucide-react'
import TopBar from '../components/TopBar'
import NavigationMap from '../components/NavigationMap'
import SystemMetrics from '../components/SystemMetrics'
import GnssStatusPanel from '../components/GnssStatusPanel'
import AlgorithmPanel from '../components/AlgorithmPanel'
import LiveCharts from '../components/LiveCharts'
import SimulationControls from '../components/SimulationControls'
import AnalyticsPage from '../components/AnalyticsPage'
import useSimulationSocket from '../hooks/useSimulationSocket'
import api from '../services/api'

const DEFAULT_SCENARIO = {
  scenario: 'outage',
  outage_start_s: 20,
  outage_duration_s: 30,
  drift_onset_s: 15,
  drift_rate_ms: 0.6,
  drift_max_m: 120,
  spoof_onset_s: 18,
  spoof_jump_m: 60,
  spoof_drift_ms: 0.8,
  spoof_heading_bias_deg: 25,
}

const DEFAULT_CONFIG = {
  scenario: DEFAULT_SCENARIO,
  noise: {
    gnss_position_sigma_m: 2.5,
    speed_sigma_ms: 0.08,
    heading_sigma_deg: 0.35,
    accel_sigma_ms2: 0.06,
    gyro_sigma_dps: 0.12,
  },
  duration_s: 120,
  rate_hz: 10,
  speed_ms: 14,
  route_pattern: 'curved',
  route_seed: 7,
  custom_waypoints: null,
  origin_lat: 26.9124,
  origin_lon: 75.7873,
  initial_heading_deg: 45,
  accel_bias_ms2: 0.035,
  gyro_bias_dps: 0.09,
  enable_map_matching: true,
  enable_ml_correction: false,
}

export default function Dashboard() {
  const [tab, setTab] = useState('dashboard')
  const [config, setConfig] = useState(DEFAULT_CONFIG)
  const [scenarios, setScenarios] = useState([])
  const [patterns, setPatterns] = useState(['straight', 'left_turn', 'right_turn', 'curved', 'random', 'custom'])
  const [route, setRoute] = useState([])
  const [outage, setOutage] = useState(null)
  const [follow, setFollow] = useState(true)
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [anomalies, setAnomalies] = useState([])
  const [mlInfo, setMlInfo] = useState(null)
  const [health, setHealth] = useState({ ok: true })

  const { connected, frame, trail, status, summary, report, lastError, clearTrail, setStatus } =
    useSimulationSocket({ renderHz: 6, maxTrail: 1200 })

  // ---------------- initial data ----------------
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const [sc, pat, info, ml, st] = await Promise.all([
          api.scenarios(),
          api.patterns(),
          api.systemInfo(),
          api.mlStatus().catch(() => null),
          api.status().catch(() => null),
        ])
        if (cancelled) return
        setScenarios(sc)
        setPatterns(pat.patterns)
        setMlInfo(ml)
        setHealth({ ok: info !== null })
        if (st) setStatus(st)
      } catch (e) {
        setError(`Backend unreachable: ${e.message}`)
        setHealth({ ok: false })
      }
    })()
    return () => {
      cancelled = true
    }
  }, [setStatus])

  // poll health occasionally (backend may restart under compose)
  useEffect(() => {
    const id = setInterval(async () => {
      try {
        await api.health()
        setHealth({ ok: true })
      } catch {
        setHealth({ ok: false })
      }
    }, 20000)
    return () => clearInterval(id)
  }, [])

  // load route whenever a run becomes available
  const runId = status?.run_id
  useEffect(() => {
    if (!runId) {
      setRoute([])
      setOutage(null)
      return
    }
    let cancelled = false
    ;(async () => {
      try {
        const r = await api.route()
        if (cancelled) return
        setRoute(r.route || [])
        setOutage(r.outage_window ? { start_s: r.outage_window[0], end_s: r.outage_window[1] } : null)
      } catch {
        /* route is decorative; navigation still works */
      }
    })()
    return () => {
      cancelled = true
    }
  }, [runId])

  // periodic anomaly event fetch (discrete events, low frequency)
  useEffect(() => {
    if (!runId) return undefined
    const id = setInterval(async () => {
      try {
        const a = await api.anomalies()
        setAnomalies(a.events || [])
      } catch {
        /* ignore */
      }
    }, 4000)
    return () => clearInterval(id)
  }, [runId])

  // ---------------- lifecycle actions ----------------
  const withBusy = useCallback(async (fn) => {
    setBusy(true)
    setError(null)
    try {
      await fn()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }, [])

  const onStart = () =>
    withBusy(async () => {
      clearTrail()
      setAnomalies([])
      const res = await api.start(config)
      setStatus((s) => ({ ...(s || {}), state: res.state, run_id: res.run_id, session_id: res.session_id }))
    })

  const onPause = () => withBusy(async () => (await api.pause()).status && setStatus((await api.status())))
  const onResume = () => withBusy(async () => (await api.resume()).status && setStatus(await api.status()))
  const onStop = () => withBusy(async () => (await api.stop()).status && setStatus(await api.status()))
  const onReset = () =>
    withBusy(async () => {
      await api.reset()
      clearTrail()
      setAnomalies([])
      setRoute([])
      setOutage(null)
      setStatus({ state: 'idle', sim_time: 0, progress: 0 })
    })

  const state = status?.state || 'idle'
  const progress = state === 'idle' ? 0 : (status?.progress ?? 0)

  const gnssModule = frame?.modules?.gnss
  const mlEnabled = Boolean(config.enable_ml_correction)

  const headerStats = useMemo(
    () => [
      { label: 'Scenario', value: config.scenario.scenario },
      { label: 'Route', value: config.route_pattern.replace('_', ' ') },
      { label: 'Rate', value: `${config.rate_hz} Hz` },
    ],
    [config],
  )

  return (
    <div className="h-screen flex flex-col overflow-hidden">
      <TopBar
        status={status}
        frame={frame}
        connected={connected}
        heathOk={health.ok}
        onOpenSettings={() => setSettingsOpen((o) => !o)}
        settingsOpen={settingsOpen}
        onToggleSidebar={() => setSidebarOpen((o) => !o)}
      />

      <div className="flex-1 flex min-h-0">
        {/* left rail: controls */}
        {sidebarOpen && (
          <aside className="w-[286px] shrink-0 border-r border-navy-100 bg-white flex flex-col min-h-0">
            <SimulationControls
              config={config}
              setConfig={setConfig}
              scenarios={scenarios}
              patterns={patterns}
              state={state}
              busy={busy}
              progress={progress}
              onStart={onStart}
              onPause={onPause}
              onResume={onResume}
              onStop={onStop}
              onReset={onReset}
              error={error || lastError}
            />
            <div className="px-3 py-2 border-t border-navy-100 text-2xs text-navy-400 leading-snug">
              {headerStats.map((s) => (
                <div key={s.label} className="flex justify-between">
                  <span className="uppercase tracking-wider">{s.label}</span>
                  <span className="font-mono text-navy-600">{s.value}</span>
                </div>
              ))}
              <div className="mt-1 pt-1 border-t border-navy-100 text-[10px]">
                All telemetry is simulator-generated. No hardware required.
              </div>
            </div>
          </aside>
        )}

        {/* main area */}
        <main className="flex-1 min-w-0 flex flex-col">
          <div className="h-9 shrink-0 border-b border-navy-100 bg-white flex items-center px-2 gap-1">
            <button
              onClick={() => setTab('dashboard')}
              className={`tab flex items-center gap-1.5 ${tab === 'dashboard' ? 'tab-active' : ''}`}
            >
              <LayoutDashboard size={12} /> Operations
            </button>
            <button
              onClick={() => setTab('analytics')}
              className={`tab flex items-center gap-1.5 ${tab === 'analytics' ? 'tab-active' : ''}`}
            >
              <BarChart3 size={12} /> Analytics & sessions
            </button>
            <div className="ml-auto flex items-center gap-3 pr-1 text-2xs text-navy-500">
              {gnssModule ? (
                <span className="inline-flex items-center gap-1">
                  <Radio size={10} /> GNSS {gnssModule}
                </span>
              ) : null}
              {report ? (
                <span className="inline-flex items-center gap-1 text-emerald-700">
                  report ready · EKF {report.algorithms?.ekf?.rmse_m?.toFixed(2)} m RMSE
                </span>
              ) : null}
            </div>
          </div>

          {tab === 'dashboard' ? (
            <div className="flex-1 min-h-0 overflow-y-auto p-3 space-y-3">
              <div className="grid grid-cols-1 xl:grid-cols-3 gap-3">
                <div className="xl:col-span-2 h-[448px]">
                  <NavigationMap
                    frame={frame}
                    trail={trail}
                    route={route}
                    follow={follow}
                    onToggleFollow={() => setFollow((f) => !f)}
                  />
                </div>
                <div className="flex flex-col gap-3 min-h-0">
                  <GnssStatusPanel
                    frame={frame}
                    summary={summary}
                    anomalies={anomalies}
                    status={status}
                  />
                  <AlgorithmPanel frame={frame} mlEnabled={mlEnabled} />
                </div>
              </div>

              <SystemMetrics frame={frame} summary={summary} />

              <div className="grid grid-cols-1 xl:grid-cols-3 gap-3">
                <div className="xl:col-span-2">
                  <LiveCharts trail={trail} outage={outage} />
                </div>
                <div className="panel flex flex-col">
                  <div className="panel-header">
                    <h2 className="panel-title">Anomaly log</h2>
                    <span className="text-2xs text-navy-400">{anomalies.length} events</span>
                  </div>
                  <div className="flex-1 overflow-y-auto max-h-[210px] divide-y divide-navy-50">
                    {anomalies.length === 0 ? (
                      <div className="px-3 py-4 text-2xs text-navy-400">
                        No anomalies detected yet. Try the drift or spoofing scenario.
                      </div>
                    ) : (
                      anomalies
                        .slice()
                        .reverse()
                        .slice(0, 60)
                        .map((a, i) => (
                          <div key={`${a.t}-${i}`} className="px-3 py-1.5">
                            <div className="flex items-center justify-between">
                              <span className="font-mono text-2xs text-navy-800">
                                t={a.t.toFixed(1)}s · {a.anomaly_type}
                              </span>
                              <span
                                className={`chip ${a.rejected
                                  ? 'bg-red-50 text-red-700 border border-red-200'
                                  : 'bg-amber-50 text-amber-700 border border-amber-200'}`}
                              >
                                {a.rejected ? 'rejected' : 'down-weighted'}
                              </span>
                            </div>
                            <div className="text-2xs text-navy-500 leading-snug">{a.reason}</div>
                          </div>
                        ))
                    )}
                  </div>
                </div>
              </div>

              {mlInfo && !mlInfo.available ? (
                <div className="rounded border border-amber-200 bg-amber-50 px-3 py-2 text-2xs text-amber-800 flex items-start gap-2">
                  <TriangleAlert size={12} className="mt-0.5 shrink-0" />
                  <span>
                    ML correction layer is not trained in this environment — the EKF baseline is used
                    for every run. Train it with <code className="font-mono">python -m app.ml.train</code>.
                  </span>
                </div>
              ) : null}
            </div>
          ) : (
            <AnalyticsPage liveReport={report} frame={frame} />
          )}
        </main>
      </div>
    </div>
  )
}
