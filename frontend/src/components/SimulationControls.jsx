import React, { useState } from 'react'
import {
  Play, Pause, Square, RotateCcw, ChevronDown, ChevronRight, Radio, TriangleAlert,
  Route as RouteIcon, Gauge, Cpu,
} from 'lucide-react'
import Panel from './Panel'

function Field({ label, children, hint }) {
  return (
    <label className="block min-w-0">
      <span className="field-label">{label}</span>
      {children}
      {hint ? <span className="block text-[9px] text-slate-400 mt-[2px] leading-tight">{hint}</span> : null}
    </label>
  )
}

function Section({ title, children, defaultOpen = true, badge = null, icon: Icon }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="border-b border-slate-200/70 last:border-0">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center gap-1.5 px-3 h-[30px] text-[9.5px] font-bold uppercase tracking-[0.1em] text-slate-500 hover:text-slate-800 hover:bg-slate-50/80 transition-colors"
      >
        {open ? <ChevronDown size={11} className="text-slate-400" /> : <ChevronRight size={11} className="text-slate-400" />}
        {Icon ? <Icon size={10.5} className="text-slate-400" /> : null}
        <span className="flex-1 text-left">{title}</span>
        {badge ? (
          <span className="chip !text-[8.5px] bg-slate-100 text-slate-500 border border-slate-200/80 !rounded">{badge}</span>
        ) : null}
      </button>
      {open ? <div className="px-3 pb-3 pt-0.5 space-y-2">{children}</div> : null}
    </div>
  )
}

function Toggle({ label, checked, onChange, hint }) {
  return (
    <button
      type="button"
      onClick={() => onChange(!checked)}
      className="w-full flex items-center justify-between gap-2 py-[3px] group text-left"
      title={hint}
    >
      <span className={`text-[11.5px] leading-snug ${checked ? 'text-slate-800' : 'text-slate-500'}`}>{label}</span>
      <span
        className={`relative shrink-0 h-[16px] w-[28px] rounded-full transition-colors duration-150 ${
          checked ? 'bg-blue-600' : 'bg-slate-300'
        }`}
      >
        <span
          className={`absolute top-[2px] h-[12px] w-[12px] rounded-full bg-white shadow-sm transition-all duration-150 ${
            checked ? 'left-[14px]' : 'left-[2px]'
          }`}
        />
      </span>
    </button>
  )
}

export default function SimulationControls({
  config, setConfig, scenarios, patterns, state, busy,
  onStart, onPause, onResume, onStop, onReset, error, progress,
}) {
  const running = state === 'running'
  const paused = state === 'paused'
  const locked = running || paused
  const cfg = config
  const set = (patch) => setConfig((c) => ({ ...c, ...patch }))
  const setScenario = (patch) => setConfig((c) => ({ ...c, scenario: { ...c.scenario, ...patch } }))
  const setNoise = (patch) => setConfig((c) => ({ ...c, noise: { ...c.noise, ...patch } }))
  const scenarioInfo = scenarios.find((s) => s.id === cfg.scenario.scenario)

  return (
    <Panel
      title="Mission control"
      icon={Cpu}
      dense
      className="min-h-0"
      actions={<span className="font-mono text-[9.5px] text-slate-400">{progress != null ? `${(progress * 100).toFixed(0)}%` : ''}</span>}
    >
      <div className="px-3 py-2.5 border-b border-slate-200/70 bg-gradient-to-b from-white to-slate-50/60 sticky top-0 z-10">
        <div className="grid grid-cols-4 gap-1.5">
          <button className="btn-primary col-span-2 !py-[7px]" disabled={busy || running} onClick={onStart} title="Start simulation">
            <Play size={11.5} strokeWidth={2.6} /> {paused ? 'Restart' : 'Start run'}
          </button>
          <button className="btn-secondary !px-0" disabled={busy || !running} onClick={onPause} title="Pause">
            <Pause size={12} />
          </button>
          <button className="btn-secondary !px-0" disabled={busy || !paused} onClick={onResume} title="Resume">
            <Play size={12} />
          </button>
        </div>
        <div className="grid grid-cols-2 gap-1.5 mt-1.5">
          <button className="btn-danger !py-[6px]" disabled={busy || (!running && !paused)} onClick={onStop} title="Stop and score this run">
            <Square size={10} strokeWidth={2.6} /> Stop
          </button>
          <button className="btn-secondary !py-[6px]" disabled={busy} onClick={onReset} title="Reset simulation state">
            <RotateCcw size={10.5} /> Reset
          </button>
        </div>
        <div className="mt-2 flex items-center gap-2">
          <div className="flex-1 h-[3px] rounded-full bg-slate-200/80 overflow-hidden">
            <div
              className="h-full rounded-full bg-gradient-to-r from-blue-600 to-sky-400 transition-all duration-300"
              style={{ width: `${Math.min(100, (progress || 0) * 100)}%` }}
            />
          </div>
          <span className={`chip !text-[8.5px] !rounded !px-1.5 ${
            running ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
              : paused ? 'bg-amber-50 text-amber-700 border border-amber-200'
                : 'bg-slate-100 text-slate-500 border border-slate-200'
          }`}>
            {state}
          </span>
        </div>
      </div>

      {error ? (
        <div className="mx-3 mt-2 rounded-lg border border-red-200 bg-red-50 px-2 py-1.5 text-[10px] text-red-700 leading-snug">
          {error}
        </div>
      ) : null}

      <div className="overflow-y-auto scroll-quiet max-h-[calc(100vh-330px)]">
        <Section title="Scenario" icon={TriangleAlert} badge={cfg.scenario.scenario}>
          <select
            className="field-input !font-sans !font-medium"
            value={cfg.scenario.scenario}
            disabled={locked}
            onChange={(e) =>
              setConfig((c) => ({
                ...c,
                scenario: { ...c.scenario, scenario: e.target.value },
                route_pattern: e.target.value === 'complex' ? 'random' : c.route_pattern,
              }))
            }
          >
            {scenarios.map((s) => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>
          {scenarioInfo ? (
            <p className="text-[10px] text-slate-500 leading-snug">{scenarioInfo.description}</p>
          ) : null}

          {cfg.scenario.scenario === 'outage' && (
            <div className="grid grid-cols-2 gap-2">
              <Field label="Outage start (s)">
                <input type="number" min="0" step="1" className="field-input" value={cfg.scenario.outage_start_s}
                  onChange={(e) => setScenario({ outage_start_s: Number(e.target.value) })} />
              </Field>
              <Field label="Duration (s)">
                <input type="number" min="1" step="1" className="field-input" value={cfg.scenario.outage_duration_s}
                  onChange={(e) => setScenario({ outage_duration_s: Number(e.target.value) })} />
              </Field>
            </div>
          )}
          {cfg.scenario.scenario === 'drift' && (
            <div className="grid grid-cols-2 gap-2">
              <Field label="Onset (s)">
                <input type="number" min="0" step="1" className="field-input" value={cfg.scenario.drift_onset_s}
                  onChange={(e) => setScenario({ drift_onset_s: Number(e.target.value) })} />
              </Field>
              <Field label="Rate (m/s)">
                <input type="number" min="0" step="0.1" className="field-input" value={cfg.scenario.drift_rate_ms}
                  onChange={(e) => setScenario({ drift_rate_ms: Number(e.target.value) })} />
              </Field>
              <Field label="Max bias (m)">
                <input type="number" min="0" step="10" className="field-input" value={cfg.scenario.drift_max_m}
                  onChange={(e) => setScenario({ drift_max_m: Number(e.target.value) })} />
              </Field>
            </div>
          )}
          {cfg.scenario.scenario === 'spoofing' && (
            <div className="grid grid-cols-2 gap-2">
              <Field label="Onset (s)">
                <input type="number" min="0" step="1" className="field-input" value={cfg.scenario.spoof_onset_s}
                  onChange={(e) => setScenario({ spoof_onset_s: Number(e.target.value) })} />
              </Field>
              <Field label="Jump (m)">
                <input type="number" min="0" step="5" className="field-input" value={cfg.scenario.spoof_jump_m}
                  onChange={(e) => setScenario({ spoof_jump_m: Number(e.target.value) })} />
              </Field>
              <Field label="Walk rate (m/s)">
                <input type="number" min="0" step="0.1" className="field-input" value={cfg.scenario.spoof_drift_ms}
                  onChange={(e) => setScenario({ spoof_drift_ms: Number(e.target.value) })} />
              </Field>
            </div>
          )}
        </Section>

        <Section title="Vehicle & route" icon={RouteIcon} badge={cfg.route_pattern.replace('_', ' ')}>
          <Field label="Movement pattern">
            <select className="field-input !font-sans !font-medium" value={cfg.route_pattern}
              disabled={locked || cfg.scenario.scenario === 'complex'}
              title={cfg.scenario.scenario === 'complex' ? 'Complex scenario uses a randomised route' : ''}
              onChange={(e) => set({ route_pattern: e.target.value })}>
              {patterns.map((p) => (<option key={p} value={p}>{p.replace(/_/g, ' ')}</option>))}
            </select>
          </Field>
          <div className="grid grid-cols-2 gap-2">
            <Field label="Speed (m/s)"><input type="number" min="0" max="80" step="1" className="field-input" value={cfg.speed_ms} onChange={(e) => set({ speed_ms: Number(e.target.value) })} /></Field>
            <Field label="Duration (s)"><input type="number" min="5" max="1800" step="5" className="field-input" value={cfg.duration_s} onChange={(e) => set({ duration_s: Number(e.target.value) })} /></Field>
            <Field label="Rate (Hz)"><input type="number" min="1" max="50" step="1" className="field-input" value={cfg.rate_hz} onChange={(e) => set({ rate_hz: Number(e.target.value) })} /></Field>
            <Field label="Heading (°)"><input type="number" min="-360" max="360" step="5" className="field-input" value={cfg.initial_heading_deg} onChange={(e) => set({ initial_heading_deg: Number(e.target.value) })} /></Field>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <Field label="Origin lat"><input type="number" step="0.0001" className="field-input" value={cfg.origin_lat} onChange={(e) => set({ origin_lat: Number(e.target.value) })} /></Field>
            <Field label="Origin lon"><input type="number" step="0.0001" className="field-input" value={cfg.origin_lon} onChange={(e) => set({ origin_lon: Number(e.target.value) })} /></Field>
          </div>
          <Field label="Route seed"><input type="number" min="0" step="1" className="field-input" value={cfg.route_seed} onChange={(e) => set({ route_seed: Number(e.target.value) })} /></Field>
        </Section>

        <Section title="Sensor noise (1σ)" icon={Gauge} defaultOpen={false}>
          <div className="grid grid-cols-2 gap-2">
            <Field label="GNSS pos (m)"><input type="number" min="0" step="0.1" className="field-input" value={cfg.noise.gnss_position_sigma_m} onChange={(e) => setNoise({ gnss_position_sigma_m: Number(e.target.value) })} /></Field>
            <Field label="Speed (m/s)"><input type="number" min="0" step="0.01" className="field-input" value={cfg.noise.speed_sigma_ms} onChange={(e) => setNoise({ speed_sigma_ms: Number(e.target.value) })} /></Field>
            <Field label="Heading (°)"><input type="number" min="0" step="0.05" className="field-input" value={cfg.noise.heading_sigma_deg} onChange={(e) => setNoise({ heading_sigma_deg: Number(e.target.value) })} /></Field>
            <Field label="Accel (m/s²)"><input type="number" min="0" step="0.01" className="field-input" value={cfg.noise.accel_sigma_ms2} onChange={(e) => setNoise({ accel_sigma_ms2: Number(e.target.value) })} /></Field>
            <Field label="Gyro (°/s)"><input type="number" min="0" step="0.01" className="field-input" value={cfg.noise.gyro_sigma_dps} onChange={(e) => setNoise({ gyro_sigma_dps: Number(e.target.value) })} /></Field>
            <Field label="Accel bias" hint="true IMU bias"><input type="number" step="0.005" className="field-input" value={cfg.accel_bias_ms2} onChange={(e) => set({ accel_bias_ms2: Number(e.target.value) })} /></Field>
          </div>
        </Section>

        <Section title="Modules" icon={Radio} defaultOpen={false}>
          <Toggle label="Map matching" checked={!!cfg.enable_map_matching} onChange={(v) => set({ enable_map_matching: v })} hint="Snap the fused track to the road network (advisory)" />
          <Toggle label="Map-aided constraint" checked={!!cfg.enable_map_aiding} onChange={(v) => set({ enable_map_aiding: v })} hint="Gated cross-track aid, applied only while coasting" />
          <Toggle label="OpenStreetMap roads" checked={!!cfg.use_real_map_data} onChange={(v) => set({ use_real_map_data: v })} hint="Fetch real road geometry (cached); falls back to synthetic" />
          <Toggle label="ML drift correction" checked={!!cfg.enable_ml_correction} onChange={(v) => set({ enable_ml_correction: v })} hint="Experimental — no measured improvement, stays off by default" />
          <p className="text-[9px] text-slate-400 leading-snug pt-1">
            Map aiding never overrides the filter. Without network access the simulator keeps its
            synthetic street graph and navigation is unaffected.
          </p>
        </Section>
      </div>
    </Panel>
  )
}
