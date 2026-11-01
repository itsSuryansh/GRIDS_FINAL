import React from 'react'
import { Cpu } from 'lucide-react'
import Panel from './Panel'
import { MODULE_STYLES } from '../utils/format'

const MODULES = [
  { key: 'gnss', label: 'GNSS receiver', desc: 'position fixes (simulated)' },
  { key: 'dead_reckoning', label: 'Dead reckoning', desc: 'IMU + odometry integration' },
  { key: 'ekf', label: 'EKF fusion', desc: '6-state filter, NIS gated' },
  { key: 'anomaly_detection', label: 'Anomaly detection', desc: '5 statistical detectors' },
  { key: 'drift_correction', label: 'Drift correction', desc: 'bounded DR correction' },
  { key: 'map_matching', label: 'Map matching', desc: 'nearest-road snapping' },
  { key: 'map_aiding', label: 'Map aiding', desc: 'cross-track pseudo-measurement' },
  { key: 'smoothing', label: 'RTS smoothing', desc: 'fixed-lag retrospective track' },
]

const MODULE_TEXT = {
  active: 'text-emerald-600',
  coasting: 'text-sky-600',
  degraded: 'text-amber-600',
  alert: 'text-red-600',
  rejected: 'text-red-600',
  unavailable: 'text-slate-400',
  idle: 'text-slate-400',
  off: 'text-slate-400',
  'n/a': 'text-slate-300',
}

const DOT = {
  active: 'bg-emerald-500',
  coasting: 'bg-sky-500',
  degraded: 'bg-amber-500',
  alert: 'bg-red-500',
  unavailable: 'bg-slate-300',
  idle: 'bg-slate-300',
  'n/a': 'bg-slate-200',
}

export default function AlgorithmPanel({ frame, mlEnabled }) {
  const mods = frame?.modules || {}
  return (
    <Panel title="Algorithm chain" icon={Cpu} subtitle="eight stages · live state">
      <div className="grid grid-cols-1 min-[1440px]:grid-cols-2 gap-x-4 gap-y-[6px]">
        {MODULES.map((m) => {
          const state = mods[m.key] || 'idle'
          const style = MODULE_STYLES[state] || MODULE_STYLES.idle
          const dot = DOT[state.split(' ')[0]] || 'bg-slate-300'
          return (
            <div key={m.key} className="flex items-center gap-1.5 min-w-0" title={`${m.label} — ${m.desc}: ${state}`}>
              <span className={`h-[6px] w-[6px] rounded-full shrink-0 ${dot} ${state === 'active' ? 'animate-pulse' : ''}`} />
              <span className="text-[10.5px] text-slate-700 truncate leading-tight">{m.label}</span>
              <span className={`ml-auto text-[8.5px] uppercase tracking-[0.04em] font-bold shrink-0 ${
                MODULE_TEXT[state.split(' ')[0]] || 'text-slate-400'
              }`}>
                {state.split(' ')[0]}
              </span>
            </div>
          )
        })}
      </div>
      <div className="mt-2 pt-1.5 border-t border-slate-100 flex items-center gap-1.5 text-[9px] text-slate-400 leading-tight">
        <span className={`h-[6px] w-[6px] rounded-full ${mlEnabled ? 'bg-violet-500' : 'bg-slate-300'}`} />
        ML correction {mlEnabled ? 'enabled' : 'disabled'} · aiding is gated and never overrides the filter
      </div>
    </Panel>
  )
}
