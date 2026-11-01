import React from 'react'
import { Cpu } from 'lucide-react'
import Panel from './Panel'
import { MODULE_STYLES } from '../utils/format'

const MODULES = [
  { key: 'gnss', label: 'GNSS receiver', desc: 'position fixes (simulated)' },
  { key: 'dead_reckoning', label: 'Dead reckoning', desc: 'IMU + odometry integration' },
  { key: 'ekf', label: 'EKF fusion', desc: '6-state filter' },
  { key: 'anomaly_detection', label: 'Anomaly detection', desc: '5 statistical detectors' },
  { key: 'drift_correction', label: 'Drift correction', desc: 'bounded DR correction' },
  { key: 'map_matching', label: 'Map matching', desc: 'nearest-road snapping' },
]

export default function AlgorithmPanel({ frame, mlEnabled, mapMatch }) {
  const mods = frame?.modules || {}
  const mm = mapMatch || frame?.map_match

  return (
    <Panel title="Navigation algorithms" icon={Cpu}>
      <div className="space-y-1">
        {MODULES.map((m) => {
          const state = mods[m.key] || 'idle'
          const style = MODULE_STYLES[state] || MODULE_STYLES.idle
          return (
            <div key={m.key} className="flex items-center justify-between gap-2 py-0.5">
              <div className="min-w-0">
                <div className="text-xs font-medium text-navy-800 truncate">{m.label}</div>
                <div className="text-2xs text-navy-400 truncate">{m.desc}</div>
              </div>
              <span className={`chip shrink-0 border ${style}`}>{state}</span>
            </div>
          )
        })}
      </div>
      {mm?.matched != null && (
        <div className="mt-2 pt-2 border-t border-navy-100 text-2xs text-navy-500 leading-snug">
          <span className="font-semibold text-navy-700">Map match:</span>{' '}
          {mm.matched ? `${mm.road} · offset ${mm.offset_m?.toFixed(1)} m` : mm.reason}
        </div>
      )}
      <div className="mt-1 text-2xs text-navy-400">
        ML correction {mlEnabled ? 'enabled for this run' : 'disabled'} — see the Analytics tab for its
        measured effect.
      </div>
    </Panel>
  )
}
