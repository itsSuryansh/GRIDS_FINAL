import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * Live simulation stream over the backend WebSocket.
 *
 * The socket is a pure subscriber: the backend owns the simulation loop, so
 * reconnects (or a second browser tab) can never start duplicate loops.
 * Frames are throttled into React state at most every `renderHz` to keep the
 * dashboard responsive while the backend runs at its own rate.
 */
export default function useSimulationSocket({ renderHz = 6, maxTrail = 900 } = {}) {
  const [connected, setConnected] = useState(false)
  const [frame, setFrame] = useState(null)
  const [trail, setTrail] = useState([])
  const [status, setStatus] = useState(null)
  const [summary, setSummary] = useState(null)
  const [report, setReport] = useState(null)
  const [lastError, setLastError] = useState(null)

  const wsRef = useRef(null)
  const reconnectRef = useRef(null)
  const pendingRef = useRef(null)
  const rafRef = useRef(null)
  const lastPushRef = useRef(0)
  const unmountedRef = useRef(false)

  const pushFrame = useCallback(
    (data) => {
      setFrame(data)
      setTrail((prev) => {
        const next = prev.length >= maxTrail ? prev.slice(prev.length - maxTrail + 1) : prev.slice()
        next.push(data)
        return next
      })
    },
    [maxTrail],
  )

  const scheduleFrame = useCallback(
    (data) => {
      pendingRef.current = data
      const minGap = 1000 / renderHz
      const now = performance.now()
      if (now - lastPushRef.current >= minGap) {
        lastPushRef.current = now
        const f = pendingRef.current
        pendingRef.current = null
        pushFrame(f)
      } else if (rafRef.current == null) {
        rafRef.current = window.setTimeout(() => {
          rafRef.current = null
          lastPushRef.current = performance.now()
          if (pendingRef.current) {
            pushFrame(pendingRef.current)
            pendingRef.current = null
          }
        }, minGap - (now - lastPushRef.current))
      }
    },
    [pushFrame, renderHz],
  )

  const connect = useCallback(() => {
    if (unmountedRef.current) return
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const explicit = import.meta.env.VITE_WS_URL
    const url = explicit || `${proto}//${window.location.host}/api/ws/simulation`

    let ws
    try {
      ws = new WebSocket(url)
    } catch (err) {
      setLastError(String(err))
      return
    }
    wsRef.current = ws

    ws.onopen = () => {
      setConnected(true)
      setLastError(null)
    }
    ws.onclose = () => {
      setConnected(false)
      if (unmountedRef.current) return
      reconnectRef.current = window.setTimeout(connect, 2000)
    }
    ws.onerror = () => setLastError('WebSocket connection error')
    ws.onmessage = (event) => {
      let msg
      try {
        msg = JSON.parse(event.data)
      } catch {
        return
      }
      switch (msg.type) {
        case 'hello':
        case 'state_change':
          setStatus(msg.data)
          if (msg.data?.state === 'idle') {
            setTrail([])
            setFrame(null)
          }
          break
        case 'backfill':
          if (Array.isArray(msg.data) && msg.data.length) {
            setTrail((prev) => {
              const merged = [...msg.data, ...prev]
              return merged.slice(Math.max(0, merged.length - maxTrail))
            })
            const last = msg.data[msg.data.length - 1]
            setFrame((prev) => prev || last)
          }
          if (msg.summary) setSummary(msg.summary)
          break
        case 'navigation_update':
          scheduleFrame(msg.data)
          if (msg.status) setStatus((s) => ({ ...(s || {}), ...msg.status }))
          if (msg.summary) setSummary(msg.summary)
          break
        case 'simulation_complete':
          setReport(msg.data)
          break
        case 'error':
          setLastError(msg.data?.message || 'simulation error')
          break
        default:
          break
      }
    }
  }, [scheduleFrame, maxTrail])

  useEffect(() => {
    unmountedRef.current = false
    connect()
    return () => {
      unmountedRef.current = true
      if (reconnectRef.current) window.clearTimeout(reconnectRef.current)
      if (rafRef.current) window.clearTimeout(rafRef.current)
      if (wsRef.current && wsRef.current.readyState <= 1) wsRef.current.close()
    }
  }, [connect])

  const clearTrail = useCallback(() => {
    setTrail([])
    setFrame(null)
    setReport(null)
  }, [])

  return {
    connected,
    frame,
    trail,
    status,
    summary,
    report,
    lastError,
    clearTrail,
    setReport,
    setStatus,
  }
}
