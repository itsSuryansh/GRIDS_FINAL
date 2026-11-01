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

export default function AlgorithmPanel({ frame, mlEnabled }) {
  const mods = frame?.modules || {}
  return (
    <Panel title="Algorithm chain" icon={Cpu} subtitle="live operational status of every stage">
      <div className="grid grid-cols-1 gap-y-[3px]">
        {MODULES.map((m) => {
          const state = mods[m.key] || 'idle'
          const style = MODULE_STYLES[state] || MODULE_STYLES.idle
          return (
            <div key={m.key} className="flex items-center justify-between gap-2 py-[1px]" title={m.desc}>
              <div className="min-w-0">
                <div className="text-[11.5px] font-medium text-slate-800 truncate leading-tight">{m.label}</div>
              </div>
              <span className={`chip shrink-0 border ${style}`}>{state}</span>
            </div>
          )
        })}
      </div>
      <div className="mt-1.5 pt-1.5 border-t border-slate-200/70 text-3xs text-slate-400 leading-snug">
        ML correction {mlEnabled ? 'enabled for this run' : 'disabled'} · map aiding is gated and never
        overrides the filter.
      </div>
    </Panel>
  )
}
