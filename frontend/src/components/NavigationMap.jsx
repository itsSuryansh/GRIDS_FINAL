import React, { useEffect, useMemo, useRef, useState } from 'react'
import {
  MapContainer,
  TileLayer,
  Polyline,
  CircleMarker,
  Marker,
  Popup,
  LayerGroup,
  Circle,
  ScaleControl,
  useMap,
} from 'react-leaflet'
import L from 'leaflet'
import {
  Map as MapIcon,
  Crosshair,
  Layers as LayersIcon,
  Grid3x3,
  Globe,
  Route,
  Download,
  Maximize2,
  Minimize2,
  ChevronDown,
} from 'lucide-react'
import Panel from './Panel'
import { COLORS, ALGO_META } from '../utils/format'
import api from '../services/api'

/* ------------------------------------------------------------------ helpers */

function vehicleIcon(headingDeg, status) {
  const h = Number(headingDeg || 0)
  const accent = status === 'suspicious' ? '#dc2626' : status === 'unavailable' ? '#475569' : '#1d4ed8'
  return L.divIcon({
    className: 'vehicle-marker',
    iconSize: [56, 56],
    iconAnchor: [28, 28],
    html: `
      <div style="position:relative;width:56px;height:56px;">
        <div style="position:absolute;inset:8px;border-radius:50%;background:${accent}12"></div>
        <div style="position:absolute;inset:8px;border-radius:50%;border:1px solid ${accent}45"></div>
        <div style="position:absolute;left:28px;top:8px;width:0;height:0;transform-origin:0 20px;transform:rotate(${h}deg);">
          <div style="position:absolute;left:-13px;top:-16px;width:26px;height:22px;
                      background:linear-gradient(180deg, ${accent}66 0%, ${accent}00 100%);
                      clip-path:polygon(50% 0%, 100% 100%, 0% 100%);"></div>
        </div>
        <div style="position:absolute;left:22px;top:22px;width:12px;height:12px;border-radius:50%;
                    background:#fff;border:2.5px solid ${accent};
                    box-shadow:0 1px 4px rgba(15,23,42,0.35);"></div>
      </div>`,
  })
}

function MapResize({ trigger }) {
  const map = useMap()
  useEffect(() => {
    const t1 = setTimeout(() => map.invalidateSize(), 60)
    const t2 = setTimeout(() => map.invalidateSize(), 380)
    return () => { clearTimeout(t1); clearTimeout(t2) }
  }, [trigger, map])
  return null
}

function FollowController({ position, follow }) {
  const map = useMap()
  useEffect(() => {
    if (follow && position) map.setView(position, map.getZoom(), { animate: true })
  }, [follow, position, map])
  return null
}

/** Small badge shown when the pointer is over the map: wheel zoom is off here. */
function WheelHint() {
  const map = useMap()
  const [hover, setHover] = useState(false)
  useEffect(() => {
    const el = map.getContainer()
    const enter = () => setHover(true)
    const leave = () => setHover(false)
    el.addEventListener('mouseenter', enter)
    el.addEventListener('mouseleave', leave)
    return () => {
      el.removeEventListener('mouseenter', enter)
      el.removeEventListener('mouseleave', leave)
    }
  }, [map])
  if (!hover) return null
  return (
    <div className="leaflet-control absolute bottom-3 left-1/2 -translate-x-1/2 z-[600] pointer-events-none
                    bg-slate-900/80 text-white text-[9.5px] rounded-full px-2.5 py-[3px]">
      wheel zoom off · expand for full-screen navigation
    </div>
  )
}

function FitOnce({ boundsKey, points }) {
  const map = useMap()
  const done = useRef(null)
  useEffect(() => {
    if (points && points.length > 1 && done.current !== boundsKey) {
      const bounds = L.latLngBounds(points.map((p) => [p.lat ?? p[0], p.lon ?? p[1]]))
      map.fitBounds(bounds, { padding: [36, 36] })
      done.current = boundsKey
    }
  }, [boundsKey, points, map])
  return null
}

/** Metric graticule drawn under the tracks (works with no tile server). */
function Graticule({ centre, radiusM = 2000, stepM = 250 }) {
  const lines = useMemo(() => {
    const out = []
    const [lat0, lon0] = centre
    const mLat = 111132.0
    const mLon = 111320.0 * Math.cos((lat0 * Math.PI) / 180)
    const dLat = stepM / mLat
    const dLon = stepM / mLon
    const nLat = Math.ceil(radiusM / stepM / 2)
    const nLon = Math.ceil(radiusM / stepM / 2)
    for (let i = -nLat; i <= nLat; i += 1) {
      out.push({
        key: `h${i}`,
        major: i === 0,
        pos: [[lat0 + i * dLat, lon0 - nLon * dLon], [lat0 + i * dLat, lon0 + nLon * dLon]],
      })
    }
    for (let i = -nLon; i <= nLon; i += 1) {
      out.push({
        key: `v${i}`,
        major: i === 0,
        pos: [[lat0 - nLat * dLat, lon0 + i * dLon], [lat0 + nLat * dLat, lon0 + i * dLon]],
      })
    }
    return out
  }, [centre[0], centre[1], radiusM, stepM])

  return (
    <>
      {lines.map((l) => (
        <Polyline
          key={l.key}
          positions={l.pos}
          interactive={false}
          pathOptions={{ color: l.major ? '#c3cede' : '#dee5ef', weight: l.major ? 1.3 : 1 }}
        />
      ))}
    </>
  )
}

function LayerToggle({ on, color, label, dashed, onClick, value, dot }) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-1.5 w-full px-1.5 py-[3.5px] rounded-md hover:bg-slate-100/80 transition-colors text-left ${on ? '' : 'opacity-35'}`}
      title={`Toggle ${label}`}
    >
      {dot ? (
        <span className="inline-block h-2 w-2 rounded-full" style={{ background: color }} />
      ) : (
        <span
          className="inline-block h-[3px] w-4 rounded"
          style={{
            background: dashed ? `repeating-linear-gradient(90deg, ${color} 0 4px, transparent 4px 7px)` : color,
          }}
        />
      )}
      <span className="text-[10.5px] text-slate-700 flex-1 truncate leading-tight">{label}</span>
      {value ? <span className="font-mono text-[9px] text-slate-500 tabular-nums">{value}</span> : null}
    </button>
  )
}

/* -------------------------------------------------------------------- main */

export default function NavigationMap({
  frame,
  trail,
  route,
  roads,
  mapMatch,
  smoothedTrack,
  follow,
  onToggleFollow,
}) {
  const [basemap, setBasemap] = useState('tiles')     // 'tiles' | 'grid'
  const [expanded, setExpanded] = useState(false)
  const [legendOpen, setLegendOpen] = useState(true)
  const [prefetching, setPrefetching] = useState(false)
  const [prefetchMsg, setPrefetchMsg] = useState(null)
  const [layers, setLayers] = useState({
    truth: true, gnss: true, dr: true, ekf: true, nomap: false,
    smoothed: true, ml: true, roads: true, anomalies: true,
  })
  const toggle = (k) => setLayers((l) => ({ ...l, [k]: !l[k] }))

  const series = useMemo(() => {
    const pick = (latKey, lonKey) =>
      trail.filter((f) => f[latKey] != null && f[lonKey] != null).map((f) => [f[latKey], f[lonKey]])
    return {
      truth: pick('truth_lat', 'truth_lon'),
      gnss: pick('gnss_lat', 'gnss_lon'),
      dr: pick('dr_lat', 'dr_lon'),
      ekf: pick('ekf_lat', 'ekf_lon'),
      nomap: pick('nomap_lat', 'nomap_lon'),
      ml: pick('ml_lat', 'ml_lon'),
    }
  }, [trail])

  // Retrospective RTS track: comes from the backend (points carry their own
  // timestamp) so the live map and the report agree on the same geometry.
  const smoothedSeries = useMemo(
    () => (smoothedTrack || []).filter((p) => p.lat != null).map((p) => [p.lat, p.lon]),
    [smoothedTrack],
  )

  const outageSegments = useMemo(() => {
    const segs = []
    let cur = []
    trail.forEach((f, i) => {
      if (f.gnss_status === 'unavailable') {
        if (cur.length === 0 && i > 0) cur.push([trail[i - 1].truth_lat, trail[i - 1].truth_lon])
        cur.push([f.truth_lat, f.truth_lon])
      } else if (cur.length) {
        segs.push(cur)
        cur = []
      }
    })
    if (cur.length) segs.push(cur)
    return segs.filter((s) => s.length > 1)
  }, [trail])

  const anomalies = useMemo(
    () => trail.filter((f) => f.anomaly && f.gnss_lat != null).slice(-60),
    [trail],
  )

  const position = frame ? [frame.truth_lat, frame.truth_lon] : null
  const centre = position || [26.9124, 75.7873]
  const start = route && route.length ? [route[0].lat, route[0].lon] : null
  const roadPoints = useMemo(
    () => (roads || []).map((r) => r.points.map((p) => [p[0], p[1]])),
    [roads],
  )

  const doPrefetch = async () => {
    setPrefetching(true)
    setPrefetchMsg(null)
    try {
      const res = await api.prefetchTiles(centre[0], centre[1])
      setPrefetchMsg(res.ok ? `${res.fetched} tiles cached (${res.cached_total} total)` : res.reason)
    } catch (e) {
      setPrefetchMsg(e.message)
    } finally {
      setPrefetching(false)
    }
  }

  return (
    <Panel
      title="Navigation map"
      subtitle={
        roads && roads.length
          ? `${roads.length} OpenStreetMap ways · map matching ${mapMatch?.matched ? 'locked' : 'searching'}`
          : 'cached OpenStreetMap basemap · synthetic road network'
      }
      icon={MapIcon}
      dense
      className="h-full"
      actions={
        <>
          <span className="hidden lg:inline text-2xs text-slate-400 font-mono">{trail.length} pts</span>
          <div className="flex rounded-lg border border-slate-300/90 bg-slate-50 p-[2px] gap-[2px]">
            <button
              onClick={() => setBasemap('tiles')}
              className={`grid place-items-center h-[23px] w-[23px] rounded-md transition-colors ${
                basemap === 'tiles' ? 'bg-white text-slate-800 shadow-[0_1px_2px_rgba(15,23,42,0.12)]' : 'text-slate-400 hover:text-slate-600'
              }`}
              title="Map tiles (cached by the backend)"
            >
              <Globe size={11.5} />
            </button>
            <button
              onClick={() => setBasemap('grid')}
              className={`grid place-items-center h-[23px] w-[23px] rounded-md transition-colors ${
                basemap === 'grid' ? 'bg-white text-slate-800 shadow-[0_1px_2px_rgba(15,23,42,0.12)]' : 'text-slate-400 hover:text-slate-600'
              }`}
              title="Offline metric grid"
            >
              <Grid3x3 size={11.5} />
            </button>
          </div>
          <button className="icon-btn" onClick={doPrefetch} disabled={prefetching} title="Cache map tiles for offline use">
            <Download size={12} className={prefetching ? 'animate-bounce' : ''} />
          </button>
          <button
            className={`icon-btn ${follow ? '!bg-blue-50 !border-blue-200 !text-blue-700' : ''}`}
            onClick={onToggleFollow}
            title="Follow vehicle"
          >
            <Crosshair size={12} />
          </button>
          <button className="icon-btn" onClick={() => setExpanded((e) => !e)} title="Expand map">
            {expanded ? <Minimize2 size={12} /> : <Maximize2 size={12} />}
          </button>
        </>
      }
    >
      <div className={expanded ? 'fixed inset-0 z-30 bg-white flex flex-col' : 'relative w-full h-full'}>
        {expanded && (
          <div className="h-10 shrink-0 flex items-center gap-2 px-3 border-b border-slate-200 bg-white">
            <MapIcon size={13} className="text-slate-400" />
            <span className="text-xs font-semibold text-slate-800">Navigation map</span>
            <span className="hidden sm:inline text-2xs text-slate-400">
              {roads && roads.length ? `${roads.length} OpenStreetMap ways` : 'synthetic road network'}
            </span>
            <div className="ml-auto flex items-center gap-1">
              <button className="btn-secondary !px-2 !py-1" onClick={doPrefetch} disabled={prefetching}>
                <Download size={12} /> Cache tiles
              </button>
              <button className={`btn-secondary !px-2 !py-1 ${follow ? 'bg-slate-100' : ''}`} onClick={onToggleFollow}>
                <Crosshair size={12} /> Follow
              </button>
              <button className="btn-secondary !px-2 !py-1" onClick={() => setExpanded(false)} title="Exit full screen">
                <Minimize2 size={12} /> Exit
              </button>
            </div>
          </div>
        )}
        <div className={expanded ? 'relative flex-1 min-h-0' : 'relative w-full h-full'}>
        <MapContainer
          center={centre}
          zoom={16}
          className="h-full w-full"
          preferCanvas
          zoomControl
          scrollWheelZoom={expanded}
        >
          {basemap === 'tiles' ? (
            <TileLayer
              url={api.tileUrl('{z}', '{x}', '{y}')}
              attribution='&copy; OpenStreetMap contributors'
              maxZoom={19}
              maxNativeZoom={17}
              tileSize={256}
              keepBuffer={4}
              updateWhenIdle={false}
              errorTileUrl="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
            />
          ) : (
            <Graticule centre={centre} />
          )}
          <ScaleControl position="bottomright" imperial={false} />
          {!expanded && <WheelHint />}
          <MapResize trigger={expanded} />
          <FollowController position={position} follow={follow} />
          <FitOnce boundsKey={route?.length || 0} points={route} />

          {/* real road geometry from OpenStreetMap */}
          {layers.roads &&
            roadPoints.map((pts, i) => (
              <Polyline
                key={`road-${i}`}
                positions={pts}
                interactive={false}
                pathOptions={{ color: '#8fa3bd', weight: 1.2, opacity: 0.45 }}
              />
            ))}

          {/* planned / simulated route */}
          {route && route.length > 1 && (
            <Polyline
              positions={route.map((p) => [p.lat, p.lon])}
              pathOptions={{ color: '#94a3b8', weight: 7, opacity: 0.22 }}
            />
          )}

          {/* GNSS-denied stretches */}
          {outageSegments.map((sg, i) => (
            <Polyline
              key={`outage-${i}`}
              positions={sg}
              interactive={false}
              pathOptions={{ color: '#64748b', weight: 10, opacity: 0.18, lineCap: 'round' }}
            />
          ))}

          {/* 500 m range ring */}
          {position && (
            <Circle
              center={position}
              radius={500}
              interactive={false}
              pathOptions={{ color: '#cbd5e1', weight: 1, dashArray: '2 6', fill: false }}
            />
          )}

          <LayerGroup>
            {layers.truth && series.truth.length > 1 && (
              <Polyline positions={series.truth} pathOptions={{ color: COLORS.truth, weight: 2, opacity: 0.8 }} />
            )}
            {layers.gnss && series.gnss.length > 1 && (
              <Polyline positions={series.gnss} pathOptions={{ color: COLORS.gnss, weight: 1.6, opacity: 0.95, dashArray: '6 4' }} />
            )}
            {layers.dr && series.dr.length > 1 && (
              <Polyline positions={series.dr} pathOptions={{ color: COLORS.dr, weight: 1.5, opacity: 0.8 }} />
            )}
            {layers.nomap && series.nomap.length > 1 && (
              <Polyline positions={series.nomap} pathOptions={{ color: COLORS.ekfNomap, weight: 1.4, opacity: 0.9, dashArray: '3 3' }} />
            )}
            {layers.ekf && series.ekf.length > 1 && (
              <Polyline positions={series.ekf} pathOptions={{ color: COLORS.ekf, weight: 2.6, opacity: 0.95 }} />
            )}
            {layers.smoothed && smoothedSeries.length > 1 && (
              <Polyline positions={smoothedSeries} pathOptions={{ color: COLORS.smoothed, weight: 1.6, opacity: 0.9, dashArray: '8 5' }} />
            )}
            {layers.ml && series.ml.length > 1 && (
              <Polyline positions={series.ml} pathOptions={{ color: COLORS.ml, weight: 1.4, opacity: 0.8 }} />
            )}
          </LayerGroup>

          {/* map-matching: snapped position + offset segment */}
          {mapMatch?.lat != null && (
            <>
              <Polyline
                positions={[[mapMatch.lat, mapMatch.lon], position]}
                pathOptions={{ color: '#0d9488', weight: 1.6, opacity: 0.9 }}
              />
              <CircleMarker
                center={[mapMatch.lat, mapMatch.lon]}
                radius={5}
                pathOptions={{ color: '#0d9488', fillColor: '#ffffff', fillOpacity: 1, weight: 2 }}
              >
                <Popup>
                  <b>Map matched</b>
                  <br />
                  {mapMatch.road}
                  <br />
                  offset {mapMatch.offset_m?.toFixed(1)} m
                  {frame?.modules?.map_aiding ? (
                    <>
                      <br />
                      cross-track aiding: {frame.modules.map_aiding}
                    </>
                  ) : null}
                </Popup>
              </CircleMarker>
            </>
          )}

          {/* anomalies */}
          {layers.anomalies &&
            anomalies.map((f, i) => (
              <CircleMarker
                key={`anom-${f.t}-${i}`}
                center={[f.gnss_lat, f.gnss_lon]}
                radius={4}
                pathOptions={{ color: COLORS.anomaly, fillColor: COLORS.anomaly, fillOpacity: 0.75, weight: 1 }}
              >
                <Popup>
                  <b>GNSS anomaly · {f.anomaly_type}</b>
                  <br />
                  t = {f.t.toFixed(2)} s · score {(f.anomaly_score * 100).toFixed(0)}%
                  <br />
                  {f.anomaly_reason}
                </Popup>
              </CircleMarker>
            ))}

          {/* current fixes / estimates */}
          {layers.gnss && frame?.gnss_lat != null && (
            <CircleMarker
              center={[frame.gnss_lat, frame.gnss_lon]}
              radius={4}
              pathOptions={{ color: COLORS.gnss, fillColor: COLORS.gnss, fillOpacity: 1, weight: 1 }}
            >
              <Popup>
                GNSS fix · residual {frame.gnss_residual_m ?? '—'} m
                <br />
                status {frame.gnss_status}
              </Popup>
            </CircleMarker>
          )}
          {layers.ekf && frame && (
            <CircleMarker
              center={[frame.ekf_lat, frame.ekf_lon]}
              radius={5}
              pathOptions={{ color: COLORS.ekf, fillColor: '#fff', fillOpacity: 1, weight: 2 }}
            />
          )}

          {start && (
            <CircleMarker center={start} radius={6} pathOptions={{ color: '#059669', fillColor: '#059669', fillOpacity: 0.9, weight: 2 }}>
              <Popup>Simulation start</Popup>
            </CircleMarker>
          )}

          {frame && (
            <Marker position={[frame.truth_lat, frame.truth_lon]} icon={vehicleIcon(frame.heading_deg, frame.gnss_status)}>
              <Popup>
                <b>Vehicle (ground truth)</b>
                <br />
                {frame.truth_lat.toFixed(6)}, {frame.truth_lon.toFixed(6)}
                <br />
                {(frame.speed_ms * 3.6).toFixed(0)} km/h · {frame.heading_deg.toFixed(0)}°
                <br />
                EKF error {frame.ekf_error_m.toFixed(2)} m
                {frame.sm_error_m != null ? (
                  <>
                    <br />
                    RTS (4 s lag) {frame.sm_error_m.toFixed(2)} m
                  </>
                ) : null}
              </Popup>
            </Marker>
          )}
        </MapContainer>

        {/* layer legend */}
        <div className="absolute bottom-3 left-3 z-[500] bg-white/[0.97] border border-slate-200/90 rounded-xl shadow-float w-[192px] overflow-hidden">
          <button
            onClick={() => setLegendOpen((o) => !o)}
            className="w-full flex items-center justify-between px-2.5 h-7 text-[9px] uppercase tracking-[0.12em] font-bold text-slate-500 hover:bg-slate-50/80 transition-colors"
          >
            <span className="flex items-center gap-1.5">
              <LayersIcon size={10} /> Layers
            </span>
            <span className="flex items-center gap-1.5">
              <span className="font-mono text-[8.5px] font-semibold text-slate-400 normal-case tracking-normal">
                {Object.values(layers).filter(Boolean).length}/{Object.keys(layers).length}
              </span>
              <ChevronDown size={10} className={`transition-transform ${legendOpen ? '' : '-rotate-90'}`} />
            </span>
          </button>
          {legendOpen && (
            <div className="px-1 pb-1">
              <LayerToggle on={layers.truth} color={COLORS.truth} label="Ground truth" onClick={() => toggle('truth')} />
              <LayerToggle on={layers.gnss} color={COLORS.gnss} label="GNSS" dashed onClick={() => toggle('gnss')} value={frame?.gnss_residual_m != null ? `${frame.gnss_residual_m.toFixed(0)}m` : null} />
              <LayerToggle on={layers.dr} color={COLORS.dr} label="Dead reckoning" onClick={() => toggle('dr')} />
              <LayerToggle on={layers.nomap} color={COLORS.ekfNomap} label="EKF without map" dashed onClick={() => toggle('nomap')} />
              <LayerToggle on={layers.ekf} color={COLORS.ekf} label="EKF fusion" onClick={() => toggle('ekf')} value={frame ? `${frame.ekf_error_m.toFixed(1)}m` : null} />
              <LayerToggle on={layers.smoothed} color={COLORS.smoothed} label="RTS smoothed" dashed onClick={() => toggle('smoothed')} value={frame?.sm_error_m != null ? `${frame.sm_error_m.toFixed(1)}m` : null} />
              <LayerToggle on={layers.ml} color={COLORS.ml} label="EKF + ML" onClick={() => toggle('ml')} />
              <LayerToggle on={layers.roads} color="#94a3b8" label="OSM roads" onClick={() => toggle('roads')} />
              <div className="border-t border-slate-200 mt-1 pt-1">
                <LayerToggle on={layers.anomalies} color={COLORS.anomaly} label="Detected anomaly" dot onClick={() => toggle('anomalies')} />
                <div className="flex items-center gap-1.5 px-1.5 py-[2px]">
                  <span className="inline-block h-1.5 w-4 rounded" style={{ background: 'rgba(100,116,139,0.35)' }} />
                  <span className="text-2xs text-slate-700">GNSS outage</span>
                </div>
                <div className="flex items-center gap-1.5 px-1.5 py-[2px]">
                  <span className="inline-block h-2 w-2 rounded-full border-2 border-teal-600 bg-white" />
                  <span className="text-2xs text-slate-700">Map matched</span>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* live readout */}
        {frame && (
          <div className="absolute top-3 right-3 z-[500] bg-white/[0.97] border border-slate-200/90 rounded-xl shadow-float w-[196px] overflow-hidden">
            <div className="flex items-center justify-between px-2.5 h-6 border-b border-slate-200/80 bg-slate-50/60">
              <span className="text-[8.5px] uppercase tracking-[0.12em] font-bold text-slate-500">Live position</span>
              <span className={`h-1.5 w-1.5 rounded-full ${
                frame.gnss_status === 'healthy' ? 'bg-emerald-500' : frame.gnss_status === 'unavailable' ? 'bg-slate-400' : 'bg-amber-500'
              }`} />
            </div>
            <div className="px-2.5 py-1.5 font-mono text-[10.5px] text-slate-800 leading-[1.45]">
              <div className="flex justify-between gap-2">
                <span className="text-slate-400">LAT</span><span>{frame.truth_lat.toFixed(6)}</span>
              </div>
              <div className="flex justify-between gap-2">
                <span className="text-slate-400">LON</span><span>{frame.truth_lon.toFixed(6)}</span>
              </div>
              <div className="flex justify-between gap-2 pt-1 mt-1 border-t border-slate-100">
                <span className="text-slate-400">HDG</span><span>{frame.heading_deg.toFixed(0)}°</span>
              </div>
              <div className="flex justify-between gap-2">
                <span className="text-slate-400">SPD</span><span>{(frame.speed_ms * 3.6).toFixed(0)} km/h</span>
              </div>
            </div>
            <div className="px-2.5 py-1 border-t border-slate-200/80 bg-teal-50/50 flex items-center gap-1.5">
              <Route size={9.5} className="text-teal-600 shrink-0" />
              <span className="text-[9.5px] text-teal-800 truncate">
                {mapMatch?.matched ? String(mapMatch.road) : 'no road match'}
              </span>
            </div>
          </div>
        )}

        {prefetchMsg && (
          <div className="absolute top-3 left-1/2 -translate-x-1/2 z-[500] bg-slate-900/90 text-white text-2xs rounded-md px-3 py-1.5">
            {prefetchMsg}
          </div>
        )}
          </div>
        </div>
    </Panel>
  )
}
