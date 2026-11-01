import React, { useState } from 'react'
import { Play, Pause, Square, RotateCcw, SlidersHorizontal, ChevronDown, ChevronRight, Zap } from 'lucide-react'
import Panel from './Panel'

function Field({ label, children, hint }) {
  return (
    <label className="block">
      <span className="field-label">{label}</span>
      {children}
      {hint ? <span className="text-3xs text-slate-400">{hint}</span> : null}
    </label>
  )
}

function Section({ title, children, defaultOpen = true, badge = null }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="border-b border-slate-200/70 last:border-0">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center gap-1.5 px-3 py-1.5 text-[10px] font-bold uppercase tracking-[0.08em] text-slate-500 hover:bg-slate-50"
      >
        {open ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
        <span className="flex-1 text-left">{title}</span>
        {badge ? <span className="chip bg-slate-100 text-slate-500 border border-slate-200">{badge}</span> : null}
      </button>
      {open ? <div className="px-3 pb-2.5 space-y-2">{children}</div> : null}
    </div>
  )
}

export default function SimulationControls({
  config, setConfig, scenarios, patterns, state, busy,
  onStart, onPause, onResume, onStop, onReset, error, progress,
}) {
  const running = state === 'running'
  const paused = state === 'paused'
  const cfg = config
  const set = (patch) => setConfig((c) => ({ ...c, ...patch }))
  const setScenario = (patch) => setConfig((c) => ({ ...c, scenario: { ...c.scenario, ...patch } }))
  const setNoise = (patch) => setConfig((c) => ({ ...c, noise: { ...c.noise, ...patch } }))
  const scenarioInfo = scenarios.find((s) => s.id === cfg.scenario.scenario)

  return (
    <Panel
      title="Mission control"
      icon={SlidersHorizontal}
      dense
      className="min-h-0"
      actions={<span className="font-mono text-3xs text-slate-400">{progress != null ? `${(progress * 100).toFixed(0)}%` : ''}</span>}
    >
      <div className="px-3 py-2 border-b border-slate-200/70 sticky top-0 bg-white z-10">
        <div className="grid grid-cols-4 gap-1.5">
          <button className="btn-primary col-span-2" disabled={busy || running} onClick={onStart} title="Start simulation">
            <Play size={12} /> {paused ? 'Restart' : 'Start'}
          </button>
          <button className="btn-secondary" disabled={busy || !running} onClick={onPause} title="Pause">
            <Pause size={12} />
          </button>
          <button className="btn-secondary" disabled={busy || !paused} onClick={onResume} title="Resume">
            <Play size={12} />
          </button>
        </div>
        <div className="grid grid-cols-2 gap-1.5 mt-1.5">
          <button className="btn-danger" disabled={busy || (!running && !paused)} onClick={onStop} title="Stop and score this run">
            <Square size={11} /> Stop
          </button>
          <button className="btn-secondary" disabled={busy} onClick={onReset} title="Reset simulation state">
            <RotateCcw size={11} /> Reset
          </button>
        </div>
        <div className="mt-2 h-1 rounded-full bg-slate-100 overflow-hidden">
          <div className="h-full bg-blue-600 transition-all duration-300" style={{ width: `${Math.min(100, (progress || 0) * 100)}%` }} />
        </div>
      </div>

      {error ? (
        <div className="mx-3 mt-2 rounded-md border border-red-200 bg-red-50 px-2 py-1 text-3xs text-red-700">{error}</div>
      ) : null}

      <div className="overflow-y-auto max-h-[calc(100vh-355px)]">
        <Section title="Scenario">
          <select
            className="field-input !font-sans"
            value={cfg.scenario.scenario}
            disabled={running || paused}
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
          {scenarioInfo ? <p className="text-3xs text-slate-500 leading-snug">{scenarioInfo.description}</p> : null}

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

        <Section title="Vehicle & route">
          <Field label="Movement pattern">
            <select className="field-input !font-sans" value={cfg.route_pattern}
              disabled={running || paused || cfg.scenario.scenario === 'complex'}
              title={cfg.scenario.scenario === 'complex' ? 'Complex scenario uses a randomised route' : ''}
              onChange={(e) => set({ route_pattern: e.target.value })}>
              {patterns.map((p) => (<option key={p} value={p}>{p.replace('_', ' ')}</option>))}
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

        <Section title="Sensor noise (1σ)" defaultOpen={false}>
          <div className="grid grid-cols-2 gap-2">
            <Field label="GNSS pos (m)"><input type="number" min="0" step="0.1" className="field-input" value={cfg.noise.gnss_position_sigma_m} onChange={(e) => setNoise({ gnss_position_sigma_m: Number(e.target.value) })} /></Field>
            <Field label="Speed (m/s)"><input type="number" min="0" step="0.01" className="field-input" value={cfg.noise.speed_sigma_ms} onChange={(e) => setNoise({ speed_sigma_ms: Number(e.target.value) })} /></Field>
            <Field label="Heading (°)"><input type="number" min="0" step="0.05" className="field-input" value={cfg.noise.heading_sigma_deg} onChange={(e) => setNoise({ heading_sigma_deg: Number(e.target.value) })} /></Field>
            <Field label="Accel (m/s²)"><input type="number" min="0" step="0.01" className="field-input" value={cfg.noise.accel_sigma_ms2} onChange={(e) => setNoise({ accel_sigma_ms2: Number(e.target.value) })} /></Field>
            <Field label="Gyro (°/s)"><input type="number" min="0" step="0.01" className="field-input" value={cfg.noise.gyro_sigma_dps} onChange={(e) => setNoise({ gyro_sigma_dps: Number(e.target.value) })} /></Field>
            <Field label="Accel bias (m/s²)" hint="true IMU bias"><input type="number" step="0.005" className="field-input" value={cfg.accel_bias_ms2} onChange={(e) => set({ accel_bias_ms2: Number(e.target.value) })} /></Field>
          </div>
        </Section>

        <Section title="Modules" defaultOpen={false}>
          {[
            ['enable_map_matching', 'Map matching'],
            ['enable_map_aiding', 'Map-aided cross-track constraint'],
            ['use_real_map_data', 'Use OpenStreetMap road data'],
            ['enable_ml_correction', 'ML drift correction (experimental)'],
          ].map(([key, label]) => (
            <label key={key} className="flex items-center justify-between gap-2 text-xs text-slate-700">
              <span>{label}</span>
              <input type="checkbox" checked={!!cfg[key]} onChange={(e) => set({ [key]: e.target.checked })} />
            </label>
          ))}
          <p className="text-3xs text-slate-400 leading-snug">
            Map aiding is a soft, gated constraint. When OpenStreetMap is unreachable the simulator
            keeps its synthetic road network and navigation is unaffected.
          </p>
        </Section>
      </div>
    </Panel>
  )
}
