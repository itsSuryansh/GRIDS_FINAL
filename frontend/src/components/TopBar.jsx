import React from 'react'
import {
  Activity,
  Satellite,
  Wifi,
  WifiOff,
  Settings,
  Play,
  Pause,
  PanelLeftClose,
  Map as MapIcon,
} from 'lucide-react'
import { STATUS_STYLES, MODULE_STYLES, clockFromSeconds } from '../utils/format'

function StatusPill({ label, value, style, icon: Icon, title }) {
  return (
    <div className="flex items-center gap-1.5" title={title}>
      <span className="text-2xs uppercase tracking-wider text-slate-400 hidden 2xl:inline">{label}</span>
      <span className={`chip ${style}`}>
        {Icon ? <Icon size={10} /> : null}
        {value}
      </span>
    </div>
  )
}

export default function TopBar({
  status,
  frame,
  connected,
  healthOk,
  latencyMs,
  mapMode,
  onToggleSidebar,
  sidebarOpen,
  onOpenSettings,
  settingsOpen,
}) {
  const state = status?.state || 'idle'
  const gnss = frame?.gnss_status || 'unavailable'
  const simChip =
    state === 'running' ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
      : state === 'paused' ? 'bg-amber-50 text-amber-700 border border-amber-200'
        : state === 'completed' ? 'bg-sky-50 text-sky-700 border border-sky-200'
          : state === 'stopped' ? 'bg-slate-100 text-slate-600 border border-slate-200'
            : 'bg-slate-100 text-slate-500 border border-slate-200'

  return (
    <header className="h-14 shrink-0 bg-white border-b border-slate-200 flex items-center px-3 gap-4 z-30">
      <div className="flex items-center gap-2.5 min-w-0">
        <button
          onClick={onToggleSidebar}
          className={`p-1.5 rounded hover:bg-slate-100 ${sidebarOpen ? 'text-slate-500' : 'text-slate-400'}`}
          title="Toggle configuration rail"
          aria-label="Toggle configuration rail"
        >
          <PanelLeftClose size={16} className={sidebarOpen ? '' : 'rotate-180'} />
        </button>
        <img src="/grids-mark.svg" alt="GRIDS" width={30} height={30} className="rounded" />
        <div className="leading-none">
          <div className="flex items-baseline gap-2">
            <span className="text-[15px] font-bold tracking-[0.14em] text-slate-900">GRIDS</span>
            <span className="hidden xl:inline text-2xs font-medium uppercase tracking-wider text-slate-400">
              GNSS-Resilient Intelligent Dead Reckoning
            </span>
          </div>
          <div className="text-[10px] text-slate-400 mt-0.5 hidden sm:block">
            resilient positioning · sensor fusion · GNSS integrity
          </div>
        </div>
      </div>

      <div className="ml-auto flex items-center gap-3">
        <div className="hidden lg:flex items-center gap-3 pr-3 mr-1 border-r border-slate-200">
          <StatusPill label="System" value={healthOk ? 'nominal' : 'check'} style={STATUS_STYLES[healthOk ? 'healthy' : 'degraded']} icon={Activity} title="Backend and database health" />
          <StatusPill label="Sim" value={state} style={simChip} icon={state === 'running' ? Play : state === 'paused' ? Pause : Activity} title="Simulation lifecycle state" />
          <StatusPill label="GNSS" value={gnss} style={STATUS_STYLES[gnss] || STATUS_STYLES.unavailable} icon={Satellite} title="GNSS channel integrity" />
          <StatusPill
            label="Link"
            value={connected ? (latencyMs != null && latencyMs < 900 ? 'live' : 'live') : 'reconnecting'}
            style={MODULE_STYLES[connected ? 'active' : 'degraded']}
            icon={connected ? Wifi : WifiOff}
            title={connected ? 'WebSocket streaming' : 'Reconnecting to backend'}
          />
          <StatusPill
            label="Basemap"
            value={mapMode}
            style={MODULE_STYLES[mapMode === 'tiles' ? 'active' : 'idle']}
            icon={MapIcon}
            title="Map background source (tiles are cached by the backend)"
          />
        </div>

        <div className="hidden sm:flex flex-col items-end leading-tight">
          <span className="text-2xs uppercase tracking-wider text-slate-400">Mission time</span>
          <span className="font-mono text-xs text-slate-900 tabular-nums">
            {clockFromSeconds(status?.sim_time ?? frame?.t ?? 0)}
            <span className="text-slate-400"> / {clockFromSeconds(status?.duration_s ?? 0)}</span>
          </span>
        </div>

        <button
          onClick={onOpenSettings}
          className={`btn-secondary ${settingsOpen ? 'bg-slate-100' : ''}`}
          title="Simulation configuration"
        >
          <Settings size={13} />
          <span className="hidden sm:inline">Configure</span>
        </button>
      </div>
    </header>
  )
}
