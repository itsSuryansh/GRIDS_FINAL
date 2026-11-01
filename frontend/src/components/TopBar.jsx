import React from 'react'
import {
  Activity,
  Satellite,
  Wifi,
  WifiOff,
  Settings,
  Pause,
  Play,
  PanelLeftClose,
} from 'lucide-react'
import { STATUS_STYLES, MODULE_STYLES, clockFromSeconds } from '../utils/format'

function StatusPill({ label, value, style, icon: Icon }) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-2xs uppercase tracking-wider text-navy-400 hidden xl:inline">{label}</span>
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
  heathOk,
  onOpenSettings,
  settingsOpen,
  onToggleSidebar,
}) {
  const state = status?.state || 'idle'
  const gnss = frame?.gnss_status || 'unavailable'
  const simChip =
    state === 'running' ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
      : state === 'paused' ? 'bg-amber-50 text-amber-700 border border-amber-200'
        : state === 'completed' ? 'bg-sky-50 text-sky-700 border border-sky-200'
          : state === 'stopped' ? 'bg-navy-100 text-navy-600 border border-navy-200'
            : 'bg-navy-100 text-navy-500 border border-navy-200'

  return (
    <header className="h-14 shrink-0 bg-white border-b border-navy-100 flex items-center px-3 gap-4 z-20">
      <div className="flex items-center gap-2.5 min-w-0">
        <button
          onClick={onToggleSidebar}
          className="p-1.5 rounded hover:bg-navy-50 text-navy-400"
          title="Toggle configuration panel"
        >
          <PanelLeftClose size={16} />
        </button>
        <img src="/grids-mark.svg" alt="" width={28} height={28} className="rounded" />
        <div className="leading-none">
          <div className="flex items-baseline gap-2">
            <span className="text-[15px] font-bold tracking-[0.12em] text-navy-900">GRIDS</span>
            <span className="hidden lg:inline text-2xs font-medium uppercase tracking-wider text-navy-400">
              GNSS-Resilient Intelligent Dead Reckoning System
            </span>
          </div>
        </div>
      </div>

      <div className="ml-auto flex items-center gap-3">
        <div className="hidden md:flex items-center gap-3 pr-3 mr-1 border-r border-navy-100">
          <StatusPill
            label="System"
            value={heathOk ? 'nominal' : 'check'}
            style={STATUS_STYLES[heathOk ? 'healthy' : 'degraded']}
            icon={Activity}
          />
          <StatusPill
            label="Sim"
            value={state}
            style={simChip}
            icon={state === 'running' ? Play : state === 'paused' ? Pause : Activity}
          />
          <StatusPill
            label="GNSS"
            value={gnss}
            style={STATUS_STYLES[gnss] || STATUS_STYLES.unavailable}
            icon={Satellite}
          />
          <StatusPill
            label="Link"
            value={connected ? 'live' : 'reconnecting'}
            style={MODULE_STYLES[connected ? 'active' : 'degraded']}
            icon={connected ? Wifi : WifiOff}
          />
        </div>

        <div className="hidden sm:flex flex-col items-end leading-tight">
          <span className="text-2xs uppercase tracking-wider text-navy-400">Mission time</span>
          <span className="font-mono text-xs text-navy-900 tabular-nums">
            {clockFromSeconds(status?.sim_time ?? frame?.t ?? 0)}
            <span className="text-navy-400"> / {clockFromSeconds(status?.duration_s ?? 0)}</span>
          </span>
        </div>

        <button
          onClick={onOpenSettings}
          className={`btn-secondary ${settingsOpen ? 'bg-navy-50' : ''}`}
          title="Simulation configuration"
        >
          <Settings size={13} />
          <span className="hidden sm:inline">Configure</span>
        </button>
      </div>
    </header>
  )
}
