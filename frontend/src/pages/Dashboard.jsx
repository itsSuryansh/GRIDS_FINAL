import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  LayoutDashboard, BarChart3, Radio, TriangleAlert, Activity, Crosshair,
  Gauge, Route as RouteIcon, Zap,
} from 'lucide-react'
import TopBar from '../components/TopBar'
import NavigationMap from '../components/NavigationMap'
import SystemMetrics from '../components/SystemMetrics'
import GnssStatusPanel from '../components/GnssStatusPanel'
import AlgorithmPanel from '../components/AlgorithmPanel'
import LiveCharts from '../components/LiveCharts'
import SimulationControls from '../components/SimulationControls'
import AnalyticsPage from '../components/AnalyticsPage'
import SettingsDrawer from '../components/SettingsDrawer'
import useSimulationSocket from '../hooks/useSimulationSocket'
import api from '../services/api'
import { fixed } from '../utils/format'

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
  route_pattern: 'road',
  route_seed: 7,
  custom_waypoints: null,
  origin_lat: 26.9124,
  origin_lon: 75.7873,
  initial_heading_deg: 45,
  accel_bias_ms2: 0.035,
  gyro_bias_dps: 0.09,
  enable_map_matching: true,
  enable_map_aiding: true,
  use_real_map_data: true,
  map_radius_m: 1500,
  enable_ml_correction: false,
}

/* --------------------------------------------------------------- mini cards */

function Trend({ label, value, sub, tone = 'default', icon: Icon }) {
  const toneClass =
    tone === 'good' ? 'text-emerald-700' : tone === 'warn' ? 'text-amber-700' : tone === 'bad' ? 'text-red-700' : 'text-slate-900'
  return (
    <div className="panel px-3 py-2 flex items-center gap-2.5 min-w-0">
      {Icon ? (
        <div className="shrink-0 rounded-md bg-slate-100 p-1.5 text-slate-500">
          <Icon size={13} />
        </div>
      ) : null}
      <div className="min-w-0">
        <div className="metric-label truncate">{label}</div>
        <div className={`metric-value text-[15px] leading-tight ${toneClass} truncate`}>{value}</div>
        {sub ? <div className="text-3xs text-slate-400 truncate">{sub}</div> : null}
      </div>
    </div>
  )
}

function AnomalyLog({ anomalies }) {
  const list = anomalies.slice().reverse().slice(0, 80)
  return (
    <div className="panel flex flex-col min-h-0">
      <div className="panel-header">
        <div className="flex items-center gap-2">
          <TriangleAlert size={13} className="text-slate-400" />
          <h2 className="panel-title">Integrity event log</h2>
        </div>
        <span className="text-3xs text-slate-400">{anomalies.length} events</span>
      </div>
      <div className="flex-1 overflow-y-auto max-h-[236px] divide-y divide-slate-100">
        {list.length === 0 ? (
          <div className="px-3 py-4 text-2xs text-slate-400">
            No anomalies detected. Try the drift or spoofing scenario to exercise the detector.
          </div>
        ) : (
          list.map((a, i) => (
            <div key={`${a.t}-${i}`} className="px-3 py-1.5 hover:bg-slate-50">
              <div className="flex items-center justify-between gap-2">
                <span className="font-mono text-2xs text-slate-800">
                  t={a.t.toFixed(1)}s · {a.anomaly_type}
                </span>
                <span className={`chip ${a.rejected ? 'bg-red-50 text-red-700 border border-red-200' : 'bg-amber-50 text-amber-700 border border-amber-200'}`}>
                  {a.rejected ? 'rejected' : 'down-weighted'}
                </span>
              </div>
              <div className="text-3xs text-slate-500 leading-snug">{a.reason}</div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}

function MapMatchCard({ frame, mapInfo }) {
  const mm = frame?.map_match
  return (
    <div className="panel flex flex-col">
      <div className="panel-header">
        <div className="flex items-center gap-2">
          <RouteIcon size={13} className="text-slate-400" />
          <h2 className="panel-title">Map matching</h2>
        </div>
        <span className={`chip ${mm?.matched ? 'bg-teal-50 text-teal-700 border border-teal-200' : 'bg-slate-100 text-slate-500 border border-slate-200'}`}>
          {mm?.matched ? 'locked' : 'searching'}
        </span>
      </div>
      <div className="p-3 text-xs space-y-1">
        <div className="flex justify-between"><span className="metric-label">Road</span><span className="font-medium text-slate-800 truncate max-w-[150px]">{mm?.road || '—'}</span></div>
        <div className="flex justify-between"><span className="metric-label">Offset</span><span className="font-mono">{fixed(mm?.offset_m, 2)} m</span></div>
        <div className="flex justify-between"><span className="metric-label">Snap gate</span><span className="font-mono">40 m</span></div>
        <div className="flex justify-between"><span className="metric-label">Cross-track aid</span><span className="font-medium">{frame?.modules?.map_aiding || 'off'}</span></div>
        <div className="flex justify-between"><span className="metric-label">Road source</span><span className="font-medium">{mapInfo?.source === 'osm' ? 'OpenStreetMap' : mapInfo?.source === 'synthetic' ? 'synthetic' : mapInfo?.source || '—'}</span></div>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ page */

export default function Dashboard() {
  const [tab, setTab] = useState('dashboard')
  const [config, setConfig] = useState(DEFAULT_CONFIG)
  const [scenarios, setScenarios] = useState([])
  const [patterns, setPatterns] = useState(['straight', 'left_turn', 'right_turn', 'curved', 'random', 'custom'])
  const [route, setRoute] = useState([])
  const [roads, setRoads] = useState([])
  const [mapInfo, setMapInfo] = useState(null)
  const [outage, setOutage] = useState(null)
  const [follow, setFollow] = useState(true)
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [anomalies, setAnomalies] = useState([])
  const [mlInfo, setMlInfo] = useState(null)
  const [smoothed, setSmoothed] = useState([])
  const [finalReport, setFinalReport] = useState(null)
  const [health, setHealth] = useState({ ok: true })
  const mapLoadedFor = useRef(null)

  const { connected, frame, trail, status, summary, report: socketReport, lastError, latencyMs, clearTrail, setStatus } =
    useSimulationSocket({ renderHz: 8, maxTrail: 2400 })
  // A report fetched after the run ended wins over the live snapshot.
  const report = finalReport || socketReport

  /* ------------------------------------------------------------ bootstrap */
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const [sc, pat, info, ml, st] = await Promise.all([
          api.scenarios(), api.patterns(), api.systemInfo(),
          api.mlStatus().catch(() => null), api.status().catch(() => null),
        ])
        if (cancelled) return
        setScenarios(sc)
        setPatterns(pat.patterns)
        setMlInfo(ml)
        setHealth({ ok: true })
        if (st) setStatus(st)
      } catch (e) {
        setError(`Backend unreachable: ${e.message}`)
        setHealth({ ok: false })
      }
    })()
    return () => { cancelled = true }
  }, [setStatus])

  useEffect(() => {
    const id = setInterval(async () => {
      try { await api.health(); setHealth({ ok: true }) } catch { setHealth({ ok: false }) }
    }, 20000)
    return () => clearInterval(id)
  }, [])

  /* --------------------------------------------------- route + road data */
  const runId = status?.run_id
  useEffect(() => {
    if (!runId) { setRoute([]); setOutage(null); return undefined }
    let cancelled = false
    ;(async () => {
      try {
        const r = await api.route()
        if (cancelled) return
        setRoute(r.route || [])
        setOutage(r.outage_window ? { start_s: r.outage_window[0], end_s: r.outage_window[1] } : null)
        setMapInfo({ source: r.map_source, osm: r.osm })
      } catch { /* route is decorative */ }
    })()
    return () => { cancelled = true }
  }, [runId])

  // real road geometry once per origin
  useEffect(() => {
    const key = `${config.origin_lat.toFixed(3)},${config.origin_lon.toFixed(3)}`
    if (!config.use_real_map_data || mapLoadedFor.current === key) return
    mapLoadedFor.current = key
    let cancelled = false
    ;(async () => {
      try {
        const data = await api.mapRoads(config.origin_lat, config.origin_lon, config.map_radius_m || 1500)
        if (!cancelled && data?.available) {
          setRoads(data.roads || [])
          setMapInfo((m) => ({ ...(m || {}), source: 'osm', ways: (data.roads || []).length }))
        } else if (!cancelled) {
          setMapInfo((m) => ({ ...(m || {}), source: 'synthetic', reason: data?.reason }))
        }
      } catch { /* offline: keep grid */ }
    })()
    return () => { cancelled = true }
  }, [config.origin_lat, config.origin_lon, config.map_radius_m, config.use_real_map_data])

  // prefetch a few tiles so the map background survives a network drop
  useEffect(() => {
    const id = setTimeout(() => {
      api.prefetchTiles(config.origin_lat, config.origin_lon).catch(() => {})
    }, 1200)
    return () => clearTimeout(id)
  }, [config.origin_lat, config.origin_lon])

  // When a run finishes, pull the definitive report over REST (the socket
  // snapshot can arrive before the backend has persisted the final scores).
  const prevState = useRef(status?.state)
  useEffect(() => {
    const prev = prevState.current
    prevState.current = status?.state
    if (!(prev === 'running' || prev === 'paused')) return undefined
    if (!['stopped', 'completed', 'idle'].includes(status?.state)) return undefined
    let cancelled = false
    const id = setTimeout(async () => {
      try {
        const r = await api.compare(true)
        if (!cancelled) setFinalReport(r)
      } catch { /* keep the socket snapshot */ }
      try {
        const sm = await api.smoothed()
        if (!cancelled && sm.available) setSmoothed(sm.points)
      } catch { /* ignore */ }
    }, 2500)
    return () => { cancelled = true; clearTimeout(id) }
  }, [status?.state])

  useEffect(() => {
    if (!runId) return undefined
    const id = setInterval(async () => {
      try { const a = await api.anomalies(); setAnomalies(a.events || []) } catch { /* ignore */ }
      try {
        const sm = await api.smoothed()
        setSmoothed(sm.available ? sm.points : [])
      } catch { /* ignore */ }
    }, 4000)
    return () => clearInterval(id)
  }, [runId])

  /* ---------------------------------------------------------- lifecycle */
  const withBusy = useCallback(async (fn) => {
    setBusy(true); setError(null)
    try { await fn() } catch (e) { setError(e.message) } finally { setBusy(false) }
  }, [])

  const onStart = () => withBusy(async () => {
    clearTrail(); setAnomalies([]); setSmoothed([]); setFinalReport(null)
    const res = await api.start(config)
    setStatus((s) => ({ ...(s || {}), state: res.state, run_id: res.run_id, session_id: res.session_id }))
  })
  const onPause = () => withBusy(async () => { await api.pause(); setStatus(await api.status()) })
  const onResume = () => withBusy(async () => { await api.resume(); setStatus(await api.status()) })
  const onStop = () => withBusy(async () => { await api.stop(); setStatus(await api.status()) })
  const onReset = () => withBusy(async () => {
    await api.reset(); clearTrail(); setAnomalies([]); setRoute([]); setOutage(null)
    setSmoothed([]); setFinalReport(null)
    setStatus({ state: 'idle', sim_time: 0, progress: 0 })
  })

  const state = status?.state || 'idle'
  const progress = state === 'idle' ? 0 : (status?.progress ?? 0)
  const mapMode = roads.length ? 'tiles' : 'grid'
  const mapMatch = useMemo(() => {
    const mm = frame?.map_match
    return mm ? { ...mm } : null
  }, [frame?.map_match])

  const kpis = [
    {
      label: 'Position error (EKF)',
      value: frame ? `${fixed(frame.ekf_error_m, 2)} m` : '—',
      sub: frame ? `DR ${fixed(frame.dr_error_m, 1)} m · RTS ${fixed(frame.sm_error_m, 1)} m` : 'awaiting run',
      tone: frame ? (frame.ekf_error_m > 15 ? 'bad' : frame.ekf_error_m > 5 ? 'warn' : 'good') : 'default',
      icon: Crosshair,
    },
    {
      label: 'GNSS availability',
      value: `${fixed(summary?.gnss_availability_pct, 1)}%`,
      sub: frame ? `residual ${fixed(frame.gnss_residual_m, 1)} m · rejected ${frame.rejected_count ?? 0}` : '',
      tone: frame?.gnss_available ? 'good' : 'warn',
      icon: Radio,
    },
    {
      label: 'Integrity events',
      value: `${summary?.anomalies ?? 0}`,
      sub: frame?.anomaly ? frame.anomaly_type : 'no active anomaly',
      tone: frame?.anomaly ? 'bad' : 'default',
      icon: TriangleAlert,
    },
    {
      label: 'Map match offset',
      value: mapMatch?.matched ? `${fixed(mapMatch.offset_m, 1)} m` : '—',
      sub: mapMatch?.road ? String(mapMatch.road).slice(0, 26) : 'no road matched',
      tone: 'default',
      icon: RouteIcon,
    },
    {
      label: 'EKF σ position',
      value: `${fixed(frame?.position_sigma_m, 2)} m`,
      sub: `√tr(P) ${fixed(frame?.uncertainty_m, 2)} m`,
      tone: frame?.position_sigma_m > 20 ? 'warn' : 'default',
      icon: Gauge,
    },
  ]

  return (
    <div className="h-screen flex flex-col overflow-hidden bg-slate-50">
      <TopBar
        status={status}
        frame={frame}
        connected={connected}
        healthOk={health.ok}
        latencyMs={latencyMs}
        mapMode={mapMode}
        onToggleSidebar={() => setSidebarOpen((o) => !o)}
        sidebarOpen={sidebarOpen}
        onOpenSettings={() => setSettingsOpen((o) => !o)}
        settingsOpen={settingsOpen}
      />

      <SettingsDrawer open={settingsOpen} onClose={() => setSettingsOpen(false)} />

      <div className="flex-1 flex min-h-0">
        {sidebarOpen && (
          <aside className="w-[292px] shrink-0 border-r border-slate-200 bg-white flex flex-col min-h-0">
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
            <div className="px-3 py-2 border-t border-slate-200 text-3xs text-slate-400 leading-relaxed">
              <div className="flex justify-between"><span className="uppercase tracking-wider">Scenario</span><span className="font-mono text-slate-600">{config.scenario.scenario}</span></div>
              <div className="flex justify-between"><span className="uppercase tracking-wider">Route</span><span className="font-mono text-slate-600">{config.route_pattern.replace('_', ' ')}</span></div>
              <div className="flex justify-between"><span className="uppercase tracking-wider">Rate</span><span className="font-mono text-slate-600">{config.rate_hz} Hz</span></div>
              <div className="flex justify-between"><span className="uppercase tracking-wider">Basemap</span><span className="font-mono text-slate-600">{mapInfo?.source === 'osm' ? 'OSM roads' : 'tile cache'}</span></div>
              <p className="mt-1 pt-1 border-t border-slate-200">
                All telemetry is simulator-generated. No hardware required.
              </p>
            </div>
          </aside>
        )}

        <main className="flex-1 min-w-0 flex flex-col">
          <div className="h-10 shrink-0 border-b border-slate-200 bg-white flex items-center px-2 gap-1">
            <button onClick={() => setTab('dashboard')} className={`tab flex items-center gap-1.5 ${tab === 'dashboard' ? 'tab-active' : ''}`}>
              <LayoutDashboard size={12} /> Operations
            </button>
            <button onClick={() => setTab('analytics')} className={`tab flex items-center gap-1.5 ${tab === 'analytics' ? 'tab-active' : ''}`}>
              <BarChart3 size={12} /> Analytics & sessions
            </button>
            <div className="ml-auto flex items-center gap-3 pr-1 text-2xs text-slate-500">
              {frame?.modules?.gnss ? (
                <span className="inline-flex items-center gap-1"><Radio size={10} /> GNSS {frame.modules.gnss}</span>
              ) : null}
              {report ? (
                <span className="inline-flex items-center gap-1 text-emerald-700 font-medium">
                  <Zap size={10} /> report ready · EKF {report.algorithms?.ekf?.rmse_m?.toFixed(2)} m RMSE
                </span>
              ) : null}
              <span className="inline-flex items-center gap-1"><Activity size={10} /> {trail.length} frames</span>
            </div>
          </div>

          {tab === 'dashboard' ? (
            <div className="flex-1 min-h-0 overflow-y-auto p-3 space-y-3">
              <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-3">
                {kpis.map((k) => (<Trend key={k.label} {...k} />))}
              </div>

              <div className="grid grid-cols-1 xl:grid-cols-3 gap-3 xl:h-[600px]">
                <div className="xl:col-span-2 h-[420px] xl:h-full">
                  <NavigationMap
                    frame={frame}
                    trail={trail}
                    route={route}
                    roads={roads}
                    mapMatch={mapMatch}
                    smoothedTrack={smoothed}
                    follow={follow}
                    onToggleFollow={() => setFollow((f) => !f)}
                  />
                </div>
                <div className="flex flex-col gap-3 min-h-0 xl:overflow-y-auto xl:pr-0.5">
                  <GnssStatusPanel frame={frame} summary={summary} anomalies={anomalies} />
                  <MapMatchCard frame={frame} mapInfo={mapInfo} />
                  <AlgorithmPanel frame={frame} mlEnabled={config.enable_ml_correction} />
                </div>
              </div>

              <SystemMetrics frame={frame} summary={summary} report={report} />

              <div className="grid grid-cols-1 xl:grid-cols-3 gap-3">
                <div className="xl:col-span-2"><LiveCharts trail={trail} outage={outage} /></div>
                <AnomalyLog anomalies={anomalies} />
              </div>

              {mlInfo && !mlInfo.available ? (
                <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-2xs text-amber-800 flex items-start gap-2">
                  <TriangleAlert size={12} className="mt-0.5 shrink-0" />
                  <span>
                    ML correction layer is not trained here — every run uses the EKF baseline. Train it with{' '}
                    <code className="font-mono">python -m app.ml.train</code>; the evaluation is shown in Analytics.
                  </span>
                </div>
              ) : null}
            </div>
          ) : (
            <AnalyticsPage liveReport={report} />
          )}
        </main>
      </div>
    </div>
  )
}
