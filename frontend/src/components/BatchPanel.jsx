import React, { useCallback, useEffect, useRef, useState } from 'react'
import { Layers3, Play, Square, Loader2, CheckCircle2, AlertTriangle, Clock } from 'lucide-react'
import api from '../services/api'
import { ALGO_META, fixed } from '../utils/format'

const ALL = ['normal', 'outage', 'drift', 'spoofing', 'complex']
const LABEL = {
  normal: 'Normal navigation',
  outage: 'GNSS outage',
  drift: 'GNSS drift',
  spoofing: 'GNSS spoofing',
  complex: 'Complex movement',
}
const ROWS = ['gnss', 'dead_reckoning', 'ekf', 'rts_smoothed']

function Chip({ tone = 'slate', children }) {
  const map = {
    slate: 'bg-slate-100 text-slate-600 border-slate-200',
    emerald: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    amber: 'bg-amber-50 text-amber-700 border-amber-200',
    red: 'bg-red-50 text-red-700 border-red-200',
    blue: 'bg-blue-50 text-blue-700 border-blue-200',
  }
  return (
    <span className={`inline-flex items-center gap-1 rounded-md border px-1.5 py-[2px] text-[9px] font-semibold uppercase tracking-[0.06em] ${map[tone]}`}>
      {children}
    </span>
  )
}

/** Small horizontal bar so the spread across scenarios is readable at a glance. */
function Bar({ value, max, color }) {
  const pct = max > 0 ? Math.max(1.5, (value / max) * 100) : 0
  return (
    <span className="block h-[5px] w-full rounded-full bg-slate-100 overflow-hidden">
      <span className="block h-full rounded-full" style={{ width: `${pct}%`, background: color }} />
    </span>
  )
}

export default function BatchPanel() {
  const [status, setStatus] = useState(null)
  const [selected, setSelected] = useState(ALL)
  const [duration, setDuration] = useState(45)
  const [seeds, setSeeds] = useState('42')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const poll = useRef(null)

  const refresh = useCallback(async () => {
    try {
      const s = await api.batchStatus()
      setStatus(s)
      return s
    } catch (err) {
      setError(String(err.message || err))
      return null
    }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  // poll while a sweep is in flight
  useEffect(() => {
    const running = status?.state === 'running'
    if (!running) { clearInterval(poll.current); return undefined }
    poll.current = setInterval(refresh, 1200)
    return () => clearInterval(poll.current)
  }, [status?.state, refresh])

  const start = async () => {
    setBusy(true); setError(null)
    try {
      const seedList = seeds
        .split(/[, ]+/)
        .map((v) => parseInt(v, 10))
        .filter((v) => Number.isFinite(v) && v >= 0)
      const s = await api.batchRun({
        scenarios: selected,
        durations_s: [Number(duration) || 45],
        seeds: seedList.length ? seedList : [42],
        rate_hz: 10,
      })
      setStatus(s)
    } catch (err) {
      setError(String(err.message || err))
    } finally {
      setBusy(false)
    }
  }

  const cancel = async () => {
    try { setStatus(await api.batchCancel()) } catch (err) { setError(String(err.message || err)) }
  }

  const toggle = (kind) =>
    setSelected((cur) => (cur.includes(kind) ? cur.filter((k) => k !== kind) : [...cur, kind]))

  const byKind = status?.byKind || {}
  const kinds = ALL.filter((k) => byKind[k])
  const running = status?.state === 'running'
  const hasResult = kinds.length > 0
  const columnMax = Object.fromEntries(
    ROWS.map((r) => [
      r,
      Math.max(1e-6, ...kinds.map((k) => byKind[k]?.estimators?.[r]?.rmse_m ?? 0)),
    ]),
  )

  return (
    <div className="panel">
      <div className="panel-header">
        <div className="flex items-center gap-2 min-w-0">
          <span className="grid place-items-center h-[21px] w-[21px] rounded-md bg-slate-100/90 text-slate-500 shrink-0">
            <Layers3 size={11.5} strokeWidth={2.4} />
          </span>
          <div className="min-w-0 leading-none">
            <h2 className="panel-title truncate">Multi-scenario sweep</h2>
            <p className="text-[9.5px] text-slate-400 truncate mt-[3px] leading-none">
              headless runs · same estimator scoring · mean ± spread across seeds
            </p>
          </div>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          {running ? (
            <>
              <Chip tone="blue"><Loader2 size={9} className="animate-spin" /> {status.completed}/{status.total}</Chip>
              <button className="btn-secondary !px-2 !py-1" onClick={cancel} title="Stop after the current run">
                <Square size={10} strokeWidth={2.6} /> Cancel
              </button>
            </>
          ) : (
            <button
              className="btn-primary !px-2.5 !py-1"
              onClick={start}
              disabled={busy || selected.length === 0}
              title="Run the selected scenarios back to back"
            >
              {busy ? <Loader2 size={11} className="animate-spin" /> : <Play size={11} strokeWidth={2.6} />}
              Run {selected.length} scenario{selected.length === 1 ? '' : 's'}
            </button>
          )}
        </div>
      </div>

      <div className="p-3 space-y-3">
        {/* controls */}
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <div className="field-label mb-1">Scenarios</div>
            <div className="flex flex-wrap gap-1">
              {ALL.map((k) => {
                const on = selected.includes(k)
                return (
                  <button
                    key={k}
                    onClick={() => toggle(k)}
                    disabled={running}
                    className={`rounded-md border px-2 py-[3px] text-[10px] font-semibold transition-colors ${
                      on
                        ? 'border-blue-300 bg-blue-50 text-blue-800'
                        : 'border-slate-200 bg-white text-slate-500 hover:bg-slate-50'
                    } ${running ? 'opacity-60' : ''}`}
                    title={LABEL[k]}
                  >
                    {k}
                  </button>
                )
              })}
            </div>
          </div>
          <div className="w-[104px]">
            <div className="field-label mb-1">Duration (s)</div>
            <input
              type="number" min="5" max="300" value={duration} disabled={running}
              onChange={(e) => setDuration(e.target.value)}
              className="w-full rounded-md border border-slate-200 px-2 py-1 text-[11px] font-mono tabular-nums"
            />
          </div>
          <div className="w-[118px]">
            <div className="field-label mb-1">Seeds</div>
            <input
              type="text" value={seeds} disabled={running}
              onChange={(e) => setSeeds(e.target.value)}
              placeholder="42"
              className="w-full rounded-md border border-slate-200 px-2 py-1 text-[11px] font-mono tabular-nums"
            />
          </div>
          {hasResult && (
            <div className="ml-auto text-right text-[9.5px] text-slate-400 leading-tight">
              <div className="inline-flex items-center gap-1">
                {status.state === 'completed'
                  ? <><CheckCircle2 size={10} className="text-emerald-600" /> completed</>
                  : status.state === 'cancelled'
                    ? <><AlertTriangle size={10} className="text-amber-600" /> cancelled</>
                    : <><Clock size={10} /> {status.state}</>}
              </div>
              <div className="font-mono tabular-nums">
                {status.completed}/{status.total} runs · {kinds.reduce((n, k) => n + (byKind[k]?.runs || 0), 0)} scored
              </div>
            </div>
          )}
        </div>

        {error && (
          <p className="rounded-md border border-red-200 bg-red-50 px-2 py-1.5 text-[10.5px] text-red-700">{error}</p>
        )}

        {/* progress */}
        {running && (
          <div className="h-[3px] w-full rounded-full bg-slate-100 overflow-hidden">
            <div
              className="h-full rounded-full bg-gradient-to-r from-blue-600 to-sky-400 transition-[width] duration-300"
              style={{ width: `${(status.progress || 0) * 100}%` }}
            />
          </div>
        )}

        {/* result table */}
        {hasResult ? (
          <div className="overflow-x-auto rounded-md border border-slate-200">
            <table className="w-full text-[11px]">
              <thead>
                <tr className="bg-slate-50/80 text-[9px] uppercase tracking-[0.1em] text-slate-400 border-b border-slate-200">
                  <th className="text-left px-2.5 py-1.5 font-semibold">Scenario</th>
                  {ROWS.map((r) => (
                    <th key={r} className="text-right px-2 py-1.5 font-semibold">
                      {ALGO_META[r]?.short || r}
                    </th>
                  ))}
                  <th className="text-right px-2.5 py-1.5 font-semibold">EKF vs GNSS</th>
                </tr>
              </thead>
              <tbody>
                {kinds.map((k) => {
                  const row = byKind[k]
                  const gain = row.ekf_vs_gnss_pct
                  return (
                    <tr key={k} className="border-b border-slate-100 last:border-0 hover:bg-slate-50/60">
                      <td className="px-2.5 py-1.5">
                        <div className="font-medium text-slate-800">{(row.label || LABEL[k] || k)}</div>
                        <div className="text-[9px] text-slate-400 font-mono">
                          {row.runs} run{row.runs === 1 ? '' : 's'} · {fixed(row.duration_s, 0)} s · seed{row.seeds?.length > 1 ? 's' : ''} {row.seeds?.join(', ')}
                        </div>
                      </td>
                      {ROWS.map((r) => {
                        const m = row.estimators?.[r]
                        const meta = ALGO_META[r] || {}
                        return (
                          <td key={r} className="px-2 py-1.5 text-right align-top">
                            <div className={`font-mono tabular-nums ${
                              r === 'ekf' ? 'font-semibold text-slate-900' : 'text-slate-600'
                            }`}>
                              {m ? fixed(m.rmse_m, 2) : '—'}
                              {m?.rmse_std_m != null ? (
                                <span className="text-[9px] text-slate-400"> ± {fixed(m.rmse_std_m, 2)}</span>
                              ) : null}
                            </div>
                            <div className="mt-1 w-[52px] ml-auto">
                              <Bar value={m?.rmse_m ?? 0} max={columnMax[r]} color={meta.color || '#94a3b8'} />
                            </div>
                          </td>
                        )
                      })}
                      <td className="px-2.5 py-1.5 text-right">
                        <span className={`font-mono tabular-nums font-semibold ${
                          gain == null ? 'text-slate-400' : gain > 0 ? 'text-emerald-700' : 'text-red-700'
                        }`}>
                          {gain == null ? '—' : `${Math.abs(gain).toFixed(1)}%`}
                        </span>
                        <div className="text-[9px] text-slate-400">
                          {gain == null ? 'not comparable' : gain >= 0 ? 'lower error' : 'higher error'}
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-[10.5px] text-slate-500 leading-relaxed">
            Runs the selected scenarios headlessly — one navigation engine per run, scored against the
            same simulated ground truth — and reports mean RMSE per estimator. The live simulation keeps
            running while a sweep is in flight.
          </p>
        )}

        {hasResult && (
          <p className="text-[9.5px] text-slate-400 leading-relaxed">
            Each scenario is scored with its own fault parameters from the catalogue, and every estimator is
            evaluated at the same timestamps. Spreads appear when you give more than one seed. All values are
            simulated.
          </p>
        )}
      </div>
    </div>
  )
}
