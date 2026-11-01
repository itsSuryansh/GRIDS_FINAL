import React from 'react'
import {
  Activity, Satellite, Wifi, WifiOff, SlidersHorizontal, Play, Pause,
  PanelLeftClose, Map as MapIcon, CircleDot,
} from 'lucide-react'
import { STATUS_STYLES, MODULE_STYLES, clockFromSeconds } from '../utils/format'

function StatusPill({ label, value, style, icon: Icon, title, pulse }) {
  return (
    <div className="flex flex-col gap-[3px] min-w-0" title={title}>
      <span className="text-[8.5px] uppercase tracking-[0.14em] text-slate-400 font-semibold leading-none">
        {label}
      </span>
      <span className={`chip ${style} !px-1.5 !py-[3px] !text-[9.5px] !rounded-md leading-none`}>
        {Icon ? <Icon size={9.5} strokeWidth={2.5} className={pulse ? 'animate-pulse' : ''} /> : null}
        <span className="leading-none">{value}</span>
      </span>
    </div>
  )
}

function Divider() {
  return <span className="h-6 w-px bg-slate-200/80" aria-hidden />
}

export default function TopBar({
  status, frame, connected, healthOk, latencyMs, mapMode,
  onToggleSidebar, sidebarOpen, onOpenSettings, settingsOpen,
}) {
  const state = status?.state || 'idle'
  const gnss = frame?.gnss_status || 'unavailable'
  const simChip =
    state === 'running' ? 'bg-emerald-50 text-emerald-700 border border-emerald-200/80'
      : state === 'paused' ? 'bg-amber-50 text-amber-700 border border-amber-200/80'
        : state === 'completed' ? 'bg-sky-50 text-sky-700 border border-sky-200/80'
          : 'bg-slate-100 text-slate-500 border border-slate-200/80'

  const simTime = status?.sim_time ?? frame?.t ?? 0
  const duration = status?.duration_s ?? 0
  const progress = duration > 0 ? Math.min(1, simTime / duration) : 0

  return (
    <header className="h-[52px] shrink-0 bg-white/85 backdrop-blur-md border-b border-slate-200/90 flex items-center px-3 gap-3 z-30 relative">
      {/* identity */}
      <div className="flex items-center gap-2.5 min-w-0">
        <button
          onClick={onToggleSidebar}
          className="icon-btn !border-transparent hover:!border-slate-200"
          title="Toggle configuration rail"
          aria-label="Toggle configuration rail"
        >
          <PanelLeftClose size={15} className={sidebarOpen ? '' : 'rotate-180'} />
        </button>
        {/* brand lockup: satellite-globe symbol + heavy wordmark + descriptor */}
        <img
          src="/grids-symbol.svg"
          alt="GRIDS"
          width={38}
          height={24}
          className="shrink-0 -ml-0.5"
        />
        <div className="min-w-0">
          <div className="flex items-baseline gap-[9px] leading-none">
            <span className="brand-wordmark text-[16px] leading-none">GRIDS</span>
            <span className="hidden xl:inline text-[8.5px] font-bold uppercase tracking-[0.15em] text-blue-600/80 leading-none">
              resilient positioning
            </span>
          </div>
          <div className="text-[9.5px] text-slate-400 mt-[4px] leading-none tracking-[-0.005em] hidden sm:block">
            GNSS-Resilient Intelligent Dead Reckoning System
          </div>
        </div>
      </div>

      <div className="ml-auto flex items-center gap-3">
        <div className="hidden lg:flex items-center gap-3">
          <StatusPill label="System" value={healthOk ? 'nominal' : 'check'} style={STATUS_STYLES[healthOk ? 'healthy' : 'degraded']} icon={Activity} title="Backend and database health" />
          <StatusPill label="Simulation" value={state} style={simChip} icon={state === 'running' ? Play : state === 'paused' ? Pause : CircleDot} title="Simulation lifecycle state" pulse={state === 'running'} />
          <StatusPill label="GNSS" value={gnss} style={STATUS_STYLES[gnss] || STATUS_STYLES.unavailable} icon={Satellite} title="GNSS channel integrity" />
          <StatusPill label="Link" value={connected ? 'live' : 'retry'} style={MODULE_STYLES[connected ? 'active' : 'degraded']} icon={connected ? Wifi : WifiOff} title={connected ? `WebSocket streaming · ${latencyMs != null ? latencyMs.toFixed(0) + ' ms' : ''}` : 'Reconnecting to backend'} />
          <StatusPill label="Basemap" value={mapMode} style={MODULE_STYLES[mapMode === 'tiles' ? 'active' : 'idle']} icon={MapIcon} title="Map background source (tiles are cached by the backend)" />
        </div>

        <Divider />

        {/* mission clock with progress rail */}
        <div className="hidden sm:block w-[132px]">
          <div className="flex items-baseline justify-between">
            <span className="text-[8.5px] uppercase tracking-[0.14em] text-slate-400 font-semibold">Mission time</span>
            <span className="font-mono text-[11px] text-slate-500 tabular-nums">{clockFromSeconds(duration)}</span>
          </div>
          <div className="font-mono text-[13.5px] font-semibold text-slate-900 tabular-nums leading-tight">
            {clockFromSeconds(simTime)}
          </div>
          <div className="mt-1 h-[3px] rounded-full bg-slate-200/80 overflow-hidden">
            <div
              className={`h-full rounded-full transition-[width] duration-300 ${state === 'running' ? 'bg-gradient-to-r from-blue-600 to-sky-400' : 'bg-slate-400'}`}
              style={{ width: `${progress * 100}%` }}
            />
          </div>
        </div>

        <button
          onClick={onOpenSettings}
          className={`btn-secondary !px-2.5 ${settingsOpen ? 'bg-slate-100 !border-slate-300' : ''}`}
          title="System, data sources and API"
        >
          <SlidersHorizontal size={13} />
          <span className="hidden sm:inline">System</span>
        </button>
      </div>
    </header>
  )
}
