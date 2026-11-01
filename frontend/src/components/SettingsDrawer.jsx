import React, { useEffect, useState } from 'react'
import {
  X, MapPin, Database, Cpu, Radio, Info, Copy, Check, RefreshCw,
} from 'lucide-react'
import api from '../services/api'

function Row({ label, value, mono = false }) {
  return (
    <div className="flex items-start justify-between gap-3 py-1 border-b border-slate-100 last:border-0">
      <span className="text-2xs text-slate-500">{label}</span>
      <span className={`text-2xs text-right ${mono ? 'font-mono' : 'font-medium'} text-slate-800 break-all`}>{value}</span>
    </div>
  )
}

export default function SettingsDrawer({ open, onClose }) {
  const [mapStatus, setMapStatus] = useState(null)
  const [systemInfo, setSystemInfo] = useState(null)
  const [health, setHealth] = useState(null)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (!open) return undefined
    let cancelled = false
    ;(async () => {
      const [m, s, h] = await Promise.all([
        api.mapStatus().catch(() => null),
        api.systemInfo().catch(() => null),
        api.health().catch(() => null),
      ])
      if (cancelled) return
      setMapStatus(m); setSystemInfo(s); setHealth(h)
    })()
    return () => { cancelled = true }
  }, [open])

  const copyApi = async () => {
    try {
      await navigator.clipboard.writeText(`${window.location.protocol}//${window.location.hostname}:8000/docs`)
      setCopied(true)
      setTimeout(() => setCopied(false), 1600)
    } catch { /* clipboard unavailable */ }
  }

  return (
    <>
      <div
        onClick={onClose}
        className={`fixed inset-0 z-40 bg-slate-900/20 transition-opacity ${open ? 'opacity-100' : 'opacity-0 pointer-events-none'}`}
      />
      <aside
        className={`fixed top-0 right-0 z-50 h-full w-[330px] bg-white border-l border-slate-200 shadow-xl flex flex-col transition-transform duration-200 ${open ? 'translate-x-0' : 'translate-x-full'}`}
        aria-hidden={!open}
      >
        <div className="flex items-center gap-2 px-3 h-11 border-b border-slate-200">
          <Info size={13} className="text-slate-400" />
          <h2 className="panel-title flex-1">System & data sources</h2>
          <button className="btn-secondary !px-1.5 !py-1" onClick={onClose} title="Close"><X size={12} /></button>
        </div>

        <div className="flex-1 overflow-y-auto p-3 space-y-4 text-xs">
          <section>
            <h3 className="field-label flex items-center gap-1"><Cpu size={11} /> Runtime</h3>
            <Row label="Version" value={health?.version || '—'} mono />
            <Row label="Backend" value={health?.status === 'ok' ? 'healthy' : 'unreachable'} />
            <Row label="Database" value={health?.database || '—'} />
            <Row label="Uptime" value={health?.uptime_s != null ? `${health.uptime_s.toFixed(0)} s` : '—'} mono />
            <Row label="Rate" value={systemInfo?.rate_hz ? `${systemInfo.rate_hz} Hz` : '—'} />
          </section>

          <section>
            <h3 className="field-label flex items-center gap-1"><MapPin size={11} /> Map data</h3>
            <Row label="Online map data" value={mapStatus?.online_enabled ? 'enabled' : 'disabled'} />
            <Row label="Cached tiles" value={mapStatus?.cached_tiles ?? '—'} mono />
            <Row label="Tile source" value={(mapStatus?.tile_sources || [])[0] || '—'} mono />
            <Row label="Road source" value="OpenStreetMap map-data API, Overpass fallback" />
            <p className="text-3xs text-slate-400 mt-1 leading-snug">
              Tiles and road geometry are cached on disk. With no network the dashboard
              draws its cached basemap and the simulator keeps its synthetic street graph,
              so navigation and every metric stay available.
            </p>
          </section>

          <section>
            <h3 className="field-label flex items-center gap-1"><Database size={11} /> API</h3>
            <div className="flex items-center gap-1.5">
              <code className="flex-1 rounded border border-slate-200 bg-slate-50 px-1.5 py-1 text-3xs font-mono truncate">
                /docs · OpenAPI
              </code>
              <button className="btn-secondary !px-1.5 !py-1" onClick={copyApi} title="Copy backend URL">
                {copied ? <Check size={11} /> : <Copy size={11} />}
              </button>
            </div>
            <Row label="Endpoints" value="30 REST paths + 1 WebSocket" mono />
          </section>

          <section>
            <h3 className="field-label flex items-center gap-1"><Radio size={11} /> Honest limitations</h3>
            <ul className="text-3xs text-slate-500 list-disc list-inside space-y-1 leading-snug">
              <li>Every value on screen comes from the simulated run — no recorded or sample data.</li>
              <li>GNSS drift is a bias the filter cannot observe; it will follow the bias once the
                anomaly detector has to accept the channel again. This is documented, not hidden.</li>
              <li>Map aiding never overrides the filter: it is gated by match confidence and is
                disabled automatically when it disagrees with the receiver.</li>
              <li>The RTS track is retrospective (4 s behind live) and is scored at its own timestamps.</li>
            </ul>
          </section>
        </div>

        <div className="px-3 py-2 border-t border-slate-200 flex items-center justify-between text-3xs text-slate-400">
          <span>GRIDS · GNSS-Resilient Intelligent Dead Reckoning System</span>
          <RefreshCw size={10} />
        </div>
      </aside>
    </>
  )
}
