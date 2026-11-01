import React, { useEffect, useState } from 'react'
import {
  X, MapPin, Database, Cpu, Radio, Info, Copy, Check, RefreshCw,
} from 'lucide-react'
import api from '../services/api'

function Row({ label, value, mono = false }) {
  return (
    <div className="flex items-start justify-between gap-3 py-[5px] border-b border-slate-100/90 last:border-0">
      <span className="text-[10.5px] text-slate-500 whitespace-nowrap">{label}</span>
      <span
        className={`text-[10.5px] text-right leading-[1.45] min-w-0 ${
          mono ? 'font-mono tabular-nums' : 'font-medium'
        } text-slate-800 break-words`}
      >
        {value}
      </span>
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

  // Escape closes the drawer (the scrim was swallowing clicks, so this is the
  // reliable dismissal path alongside the X button).
  useEffect(() => {
    if (!open) return undefined
    const onKey = (e) => { if (e.key === 'Escape') onClose?.() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

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
        aria-hidden="true"
        className={`fixed inset-0 z-40 bg-slate-900/20 backdrop-blur-[1px] transition-opacity duration-200 ${
          open ? 'opacity-100' : 'opacity-0 pointer-events-none'
        }`}
      />
      <aside
        className={`fixed top-0 right-0 z-50 h-full w-[344px] bg-white border-l border-slate-200 shadow-float flex flex-col transition-transform duration-200 ease-out ${open ? 'translate-x-0' : 'translate-x-full'}`}
        aria-hidden={!open}
      >
        <div className="flex items-center gap-2 px-3 h-[52px] border-b border-slate-200 shrink-0">
          <span className="grid place-items-center h-[21px] w-[21px] rounded-md bg-slate-100 text-slate-500">
            <Info size={11.5} strokeWidth={2.4} />
          </span>
          <div className="flex-1 min-w-0 leading-none">
            <h2 className="panel-title truncate">System & data sources</h2>
            <p className="text-[9.5px] text-slate-400 mt-[3px] leading-none">runtime · map provenance · API</p>
          </div>
          <button className="icon-btn" onClick={onClose} title="Close"><X size={12} /></button>
        </div>

        <div className="flex-1 overflow-y-auto scroll-quiet px-3.5 py-3 space-y-4">
          <section>
            <h3 className="divider-label flex items-center gap-1.5 mb-1"><Cpu size={10.5} /> Runtime</h3>
            <Row label="Version" value={health?.version || '—'} mono />
            <Row label="Backend" value={health?.status === 'ok' ? 'healthy' : 'unreachable'} />
            <Row label="Database" value={health?.database || '—'} />
            <Row label="Uptime" value={health?.uptime_s != null ? `${health.uptime_s.toFixed(0)} s` : '—'} mono />
            <Row label="Rate" value={systemInfo?.rate_hz ? `${systemInfo.rate_hz} Hz` : '—'} />
          </section>

          <section>
            <h3 className="divider-label flex items-center gap-1.5 mb-1"><MapPin size={10.5} /> Map data</h3>
            <Row label="Online map data" value={mapStatus?.online_enabled ? 'enabled' : 'disabled'} />
            <Row
              label="Cached tiles"
              value={mapStatus?.cached_tiles != null ? mapStatus.cached_tiles.toLocaleString('en-US') : '—'}
              mono
            />
            <Row label="Tile source" value={(mapStatus?.tile_sources || [])[0] || '—'} mono />
            <Row label="Road source" value="OpenStreetMap map-data API, Overpass fallback" />
            <p className="text-3xs text-slate-400 mt-1 leading-snug">
              Tiles and road geometry are cached on disk. With no network the dashboard
              draws its cached basemap and the simulator keeps its synthetic street graph,
              so navigation and every metric stay available.
            </p>
          </section>

          <section>
            <h3 className="divider-label flex items-center gap-1.5 mb-1"><Database size={10.5} /> API</h3>
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
            <h3 className="divider-label flex items-center gap-1.5 mb-1"><Radio size={10.5} /> Honest limitations</h3>
            <ul className="text-[10px] text-slate-500 space-y-1.5 leading-[1.5]">
              <li className="relative pl-2.5 before:absolute before:left-0 before:top-[5px] before:h-[3px] before:w-[3px] before:rounded-full before:bg-slate-300">
                Every value on screen comes from the simulated run — no recorded or sample data.
              </li>
              <li className="relative pl-2.5 before:absolute before:left-0 before:top-[5px] before:h-[3px] before:w-[3px] before:rounded-full before:bg-slate-300">
                GNSS drift is a bias the filter cannot observe; it follows the bias again once the anomaly
                detector re-accepts the channel. Documented, not hidden.
              </li>
              <li className="relative pl-2.5 before:absolute before:left-0 before:top-[5px] before:h-[3px] before:w-[3px] before:rounded-full before:bg-slate-300">
                Map aiding never overrides the filter: it is gated by match confidence and switches off
                automatically when it disagrees with the receiver.
              </li>
              <li className="relative pl-2.5 before:absolute before:left-0 before:top-[5px] before:h-[3px] before:w-[3px] before:rounded-full before:bg-slate-300">
                The RTS track is retrospective (4 s behind live) and is scored at its own timestamps.
              </li>
            </ul>
          </section>
        </div>

        <div className="px-3.5 py-2.5 border-t border-slate-200 flex items-center justify-between text-[9px] text-slate-400 bg-slate-50/60">
          <span>GRIDS · GNSS-Resilient Intelligent Dead Reckoning System</span>
          <RefreshCw size={10} />
        </div>
      </aside>
    </>
  )
}
