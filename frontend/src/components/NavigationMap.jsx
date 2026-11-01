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
  const accent = status === 'suspicious' ? '#dc2626' : status === 'unavailable' ? '#64748b' : '#1d4ed8'
  return L.divIcon({
    className: 'vehicle-marker',
    iconSize: [30, 30],
    iconAnchor: [15, 15],
    html: `
      <div style="position:relative;width:30px;height:30px;">
        <div style="position:absolute;inset:0;border-radius:50%;background:${accent}1f;border:1.5px solid ${accent}88"></div>
        <div style="position:absolute;left:13.5px;top:13.5px;width:3px;height:3px;border-radius:50%;background:${accent}"></div>
        <div style="position:absolute;left:14.5px;top:13px;width:12px;height:2px;background:${accent};
                    transform-origin:1px 1px;transform:rotate(${h - 90}deg);border-radius:1px"></div>
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
      className={`flex items-center gap-1.5 w-full px-1.5 py-[3px] rounded hover:bg-slate-100 text-left ${on ? '' : 'opacity-40'}`}
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
      <span className="text-2xs text-slate-700 flex-1 truncate">{label}</span>
      {value ? <span className="font-mono text-3xs text-slate-500 tabular-nums">{value}</span> : null}
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
          <div className="flex rounded-md border border-slate-300 overflow-hidden">
            <button
              onClick={() => setBasemap('tiles')}
              className={`px-1.5 py-1 ${basemap === 'tiles' ? 'bg-slate-100 text-slate-800' : 'text-slate-400'}`}
              title="Map tiles (cached by the backend)"
            >
              <Globe size={12} />
            </button>
            <button
              onClick={() => setBasemap('grid')}
              className={`px-1.5 py-1 border-l border-slate-300 ${basemap === 'grid' ? 'bg-slate-100 text-slate-800' : 'text-slate-400'}`}
              title="Offline metric grid"
            >
              <Grid3x3 size={12} />
            </button>
          </div>
          <button className="btn-secondary !px-2 !py-1" onClick={doPrefetch} disabled={prefetching} title="Cache map tiles for offline use">
            <Download size={12} className={prefetching ? 'animate-bounce' : ''} />
          </button>
          <button className={`btn-secondary !px-2 !py-1 ${follow ? 'bg-slate-100' : ''}`} onClick={onToggleFollow} title="Follow vehicle">
            <Crosshair size={12} />
          </button>
          <button className="btn-secondary !px-2 !py-1" onClick={() => setExpanded((e) => !e)} title="Expand map">
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
        <MapContainer center={centre} zoom={16} className="h-full w-full" preferCanvas zoomControl>
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
        <div className="absolute bottom-3 left-3 z-[500] bg-white/95 backdrop-blur-sm border border-slate-200 rounded-lg shadow-sm w-[186px] overflow-hidden">
          <button
            onClick={() => setLegendOpen((o) => !o)}
            className="w-full flex items-center justify-between px-2 py-1 text-3xs uppercase tracking-wider font-bold text-slate-400 hover:bg-slate-50"
          >
            <span className="flex items-center gap-1">
              <LayersIcon size={10} /> Layers
            </span>
            <ChevronDown size={10} className={legendOpen ? '' : '-rotate-90'} />
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
          <div className="absolute top-3 right-3 z-[500] bg-white/95 backdrop-blur-sm border border-slate-200 rounded-lg shadow-sm px-2.5 py-1.5 font-mono text-2xs text-slate-700 leading-relaxed">
            <div>
              <span className="text-slate-400">LAT</span> {frame.truth_lat.toFixed(6)}
            </div>
            <div>
              <span className="text-slate-400">LON</span> {frame.truth_lon.toFixed(6)}
            </div>
            <div>
              <span className="text-slate-400">HDG</span> {frame.heading_deg.toFixed(0)}°
              <span className="text-slate-400 ml-1.5">SPD</span> {(frame.speed_ms * 3.6).toFixed(0)}km/h
            </div>
            <div className="pt-0.5 mt-0.5 border-t border-slate-200 flex items-center gap-1">
              <Route size={9} className="text-teal-600" />
              <span className="text-slate-500">
                {mapMatch?.matched ? `on ${String(mapMatch.road).slice(0, 18)}` : 'no road match'}
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
