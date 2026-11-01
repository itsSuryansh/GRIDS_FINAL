import React, { useEffect, useMemo, useRef, useState } from 'react'
import {
  MapContainer,
  ScaleControl,
  TileLayer,
  Polyline,
  CircleMarker,
  Marker,
  Popup,
  LayerGroup,
  Circle,
  useMap,
} from 'react-leaflet'
import L from 'leaflet'
import { Map as MapIcon, Crosshair, Layers, Grid3x3, Globe } from 'lucide-react'
import Panel from './Panel'
import { COLORS, latlon } from '../utils/format'

const CARTO_LIGHT = 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png'
const OSM = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'
const TILE_ATTRIB =
  '&copy; OpenStreetMap contributors &copy; CARTO — <b>basemap tiles require internet</b>; GRIDS simulation data is generated locally'

function vehicleIcon(headingDeg) {
  const h = Number(headingDeg || 0)
  return L.divIcon({
    className: 'vehicle-marker',
    iconSize: [26, 26],
    iconAnchor: [13, 13],
    html: `
      <div style="position:relative;width:26px;height:26px;">
        <div style="position:absolute;inset:0;border-radius:50%;background:rgba(29,78,216,0.12);border:1px solid rgba(29,78,216,0.45)"></div>
        <div style="position:absolute;left:11px;top:11px;width:4px;height:4px;border-radius:50%;background:#1d4ed8"></div>
        <div style="position:absolute;left:12px;top:11px;width:10px;height:2px;background:#1d4ed8;
                    transform-origin:1px 1px;transform:rotate(${h - 90}deg);border-radius:1px"></div>
      </div>`,
  })
}

/** Keeps the view centred on the vehicle when follow mode is on. */
function FollowController({ position, follow }) {
  const map = useMap()
  useEffect(() => {
    if (follow && position) map.setView(position, map.getZoom(), { animate: true })
  }, [follow, position, map])
  return null
}

function FitOnce({ route }) {
  const map = useMap()
  const done = useRef(false)
  useEffect(() => {
    if (!done.current && route && route.length > 1) {
      const bounds = L.latLngBounds(route.map((p) => [p.lat, p.lon]))
      map.fitBounds(bounds, { padding: [30, 30] })
      done.current = true
    }
  }, [route, map])
  return null
}

/** Offline graticule basemap: a light metric grid drawn around the track.
 *  Keeps the map informative when external tile servers are unreachable. */
function Graticule({ centre, radiusM = 1600, stepM = 200 }) {
  // 200 m metric grid around the track: informative without tile servers
  const lines = useMemo(() => {
    const out = []
    const lat0 = centre[0]
    const lon0 = centre[1]
    const mPerDegLat = 111132.0
    const mPerDegLon = 111320.0 * Math.cos((lat0 * Math.PI) / 180)
    const dLat = stepM / mPerDegLat
    const dLon = stepM / mPerDegLon
    const nLat = Math.ceil(radiusM / stepM / 2)
    const nLon = Math.ceil(radiusM / stepM / 2)
    for (let i = -nLat; i <= nLat; i += 1) {
      const lat = lat0 + i * dLat
      out.push({ key: `h${i}`, major: i === 0, pos: [[lat, lon0 - nLon * dLon], [lat, lon0 + nLon * dLon]] })
    }
    for (let i = -nLon; i <= nLon; i += 1) {
      const lon = lon0 + i * dLon
      out.push({ key: `v${i}`, major: i === 0, pos: [[lat0 - nLat * dLat, lon], [lat0 + nLat * dLat, lon]] })
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
          pathOptions={{ color: l.major ? '#b9c7de' : '#dbe3ef', weight: l.major ? 1.4 : 1, opacity: 1 }}
        />
      ))}
    </>
  )
}

function LegendRow({ on, color, label, dashed, onClick, value }) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-1.5 w-full px-1.5 py-[3px] rounded hover:bg-navy-50 text-left ${on ? '' : 'opacity-40'}`}
      title={`Toggle ${label}`}
    >
      <span
        className="inline-block h-[3px] w-4 rounded"
        style={{
          background: dashed
            ? `repeating-linear-gradient(90deg, ${color} 0 4px, transparent 4px 7px)`
            : color,
        }}
      />
      <span className="text-2xs text-navy-700 flex-1 truncate">{label}</span>
      {value ? <span className="font-mono text-2xs text-navy-500 tabular-nums">{value}</span> : null}
    </button>
  )
}

export default function NavigationMap({ frame, trail, route, follow = true, onToggleFollow }) {
  const [basemap, setBasemap] = useState('grid')
  const [layers, setLayers] = useState({
    truth: true,
    gnss: true,
    dr: true,
    ekf: true,
    ml: true,
    uncertainty: true,
  })
  const toggle = (k) => setLayers((l) => ({ ...l, [k]: !l[k] }))

  const series = useMemo(() => {
    const pick = (latKey, lonKey) =>
      trail
        .filter((f) => f[latKey] !== null && f[lonKey] !== null && f[latKey] !== undefined)
        .map((f) => [f[latKey], f[lonKey]])
    return {
      truth: pick('truth_lat', 'truth_lon'),
      gnss: pick('gnss_lat', 'gnss_lon'),
      dr: pick('dr_lat', 'dr_lon'),
      ekf: pick('ekf_lat', 'ekf_lon'),
      ml: pick('ml_lat', 'ml_lon'),
    }
  }, [trail])

  // contiguous ground-truth segments during which GNSS was unavailable
  const outageSegments = useMemo(() => {
    const segs = []
    let cur = []
    trail.forEach((f) => {
      if (f.gnss_status === 'unavailable') {
        if (cur.length === 0 && segs.length === 0 && trail.indexOf(f) > 0) {
          const idx = trail.indexOf(f)
          cur.push([trail[idx - 1].truth_lat, trail[idx - 1].truth_lon])
        }
        cur.push([f.truth_lat, f.truth_lon])
      } else if (cur.length) {
        segs.push(cur)
        cur = []
      }
    })
    if (cur.length) segs.push(cur)
    return segs.filter((sg) => sg.length > 1)
  }, [trail])

  const anomalies = useMemo(
    () => trail.filter((f) => f.anomaly && f.gnss_lat !== null).slice(-40),
    [trail],
  )

  const position = frame ? [frame.truth_lat, frame.truth_lon] : null
  const centre = position || [26.9124, 75.7873]
  const start = route && route.length ? [route[0].lat, route[0].lon] : null

  return (
    <Panel
      title="Navigation map"
      icon={MapIcon}
      dense
      className="h-full"
      actions={
        <>
          <span className="text-2xs text-navy-400 hidden lg:inline">
            {trail.length} live samples
          </span>
          <button
            onClick={onToggleFollow}
            className={`btn-secondary !px-2 !py-1 ${follow ? 'bg-navy-50' : ''}`}
            title="Follow vehicle"
          >
            <Crosshair size={12} /> Follow
          </button>
        </>
      }
    >
      <div className="relative h-full w-full">
        <MapContainer
          center={centre}
          zoom={16}
          className="h-full w-full"
          zoomControl
          preferCanvas
          attributionControl
        >
          {basemap === 'carto' ? (
            <TileLayer url={CARTO_LIGHT} attribution={TILE_ATTRIB} subdomains="abcd" maxZoom={20} />
          ) : (
            <Graticule centre={centre} />
          )}
          <ScaleControl position="bottomright" imperial={false} />
          <FollowController position={position} follow={follow} />
          <FitOnce route={route} />

          {/* planned route */}
          {route && route.length > 1 && (
            <Polyline
              positions={route.map((p) => [p.lat, p.lon])}
              pathOptions={{ color: '#93a8cd', weight: 6, opacity: 0.35 }}
            />
          )}

          {/* GNSS outage regions (felt GNSS-denied stretches) */}
          {outageSegments.map((sg, i) => (
            <Polyline
              key={`outage-${i}`}
              positions={sg}
              interactive={false}
              pathOptions={{ color: '#5d7cb1', weight: 9, opacity: 0.22, lineCap: 'round' }}
            />
          ))}

          {/* 500 m range ring: spatial reference on the offline grid basemap */}
          {position && (
            <Circle
              center={position}
              radius={500}
              interactive={false}
              pathOptions={{ color: '#c3cfe4', weight: 1, dashArray: '2 6', fill: false }}
            />
          )}

          {/* GNSS outage shading */}
          {layers.uncertainty && frame?.gnss_status === 'unavailable' && (
            <Circle
              center={position}
              radius={Math.max(30, (frame.position_sigma_m || 0) * 60)}
              pathOptions={{ color: '#93a8cd', fillColor: '#93a8cd', fillOpacity: 0.12, weight: 1, dashArray: '4 3' }}
            />
          )}

          <LayerGroup>
            {layers.truth && series.truth.length > 1 && (
              <Polyline positions={series.truth} pathOptions={{ color: COLORS.truth, weight: 2, opacity: 0.85 }} />
            )}
            {layers.gnss && series.gnss.length > 1 && (
              <Polyline
                positions={series.gnss}
                pathOptions={{ color: COLORS.gnss, weight: 1.6, opacity: 0.9, dashArray: '6 4' }}
              />
            )}
            {layers.dr && series.dr.length > 1 && (
              <Polyline positions={series.dr} pathOptions={{ color: COLORS.dr, weight: 1.6, opacity: 0.75 }} />
            )}
            {layers.ekf && series.ekf.length > 1 && (
              <Polyline positions={series.ekf} pathOptions={{ color: COLORS.ekf, weight: 2.4, opacity: 0.95 }} />
            )}
            {layers.ml && series.ml.length > 1 && (
              <Polyline positions={series.ml} pathOptions={{ color: COLORS.ml, weight: 1.5, opacity: 0.8 }} />
            )}
          </LayerGroup>

          {/* detected anomalies */}
          {anomalies.map((f, i) => (
            <CircleMarker
              key={`anom-${f.t}-${i}`}
              center={[f.gnss_lat, f.gnss_lon]}
              radius={4}
              pathOptions={{ color: COLORS.anomaly, fillColor: COLORS.anomaly, fillOpacity: 0.7, weight: 1 }}
            >
              <Popup>
                <b>GNSS anomaly</b>
                <br />
                t = {f.t.toFixed(2)} s · score {(f.anomaly_score * 100).toFixed(0)}%
                <br />
                {f.anomaly_reason}
              </Popup>
            </CircleMarker>
          ))}

          {/* current GNSS fix */}
          {layers.gnss && frame?.gnss_lat != null && (
            <CircleMarker
              center={[frame.gnss_lat, frame.gnss_lon]}
              radius={4}
              pathOptions={{ color: COLORS.gnss, fillColor: COLORS.gnss, fillOpacity: 1, weight: 1 }}
            >
              <Popup>GNSS fix · residual {frame.gnss_residual_m ?? '—'} m</Popup>
            </CircleMarker>
          )}

          {/* EKF estimate */}
          {layers.ekf && frame && (
            <CircleMarker
              center={[frame.ekf_lat, frame.ekf_lon]}
              radius={5}
              pathOptions={{ color: COLORS.ekf, fillColor: '#fff', fillOpacity: 1, weight: 2 }}
            />
          )}

          {/* starting location */}
          {start && (
            <CircleMarker
              center={start}
              radius={6}
              pathOptions={{ color: '#0f9d58', fillColor: '#0f9d58', fillOpacity: 0.9, weight: 2 }}
            >
              <Popup>Simulation start</Popup>
            </CircleMarker>
          )}

          {/* vehicle (ground truth) */}
          {frame && (
            <Marker position={[frame.truth_lat, frame.truth_lon]} icon={vehicleIcon(frame.heading_deg)}>
              <Popup>
                <b>Vehicle (ground truth)</b>
                <br />
                {latlon(frame.truth_lat, frame.truth_lon)}
                <br />
                {(frame.speed_ms * 3.6).toFixed(0)} km/h · {frame.heading_deg.toFixed(0)}°
                <br />
                EKF error {frame.ekf_error_m.toFixed(1)} m
              </Popup>
            </Marker>
          )}
        </MapContainer>

        {/* legend / layer toggles */}
        <div className="absolute bottom-3 left-3 z-[500] bg-white/95 backdrop-blur border border-navy-100 rounded shadow-card px-1 py-1 w-[178px]">
          <div className="flex items-center justify-between px-1.5 py-0.5 text-2xs uppercase tracking-wider text-navy-400">
            <span className="flex items-center gap-1">
              <Layers size={10} /> Layers
            </span>
            <button
              onClick={() => setBasemap((b) => (b === 'grid' ? 'carto' : 'grid'))}
              className="flex items-center gap-0.5 hover:text-navy-700 normal-case tracking-normal"
              title="Switch basemap (tiles need internet)"
            >
              {basemap === 'grid' ? <Grid3x3 size={10} /> : <Globe size={10} />}
              {basemap === 'grid' ? 'grid' : 'tiles'}
            </button>
          </div>
          <LegendRow on={layers.truth} color={COLORS.truth} label="Ground truth" onClick={() => toggle('truth')} />
          <LegendRow
            on={layers.gnss}
            color={COLORS.gnss}
            label="GNSS"
            dashed
            onClick={() => toggle('gnss')}
            value={frame?.gnss_residual_m != null ? `${frame.gnss_residual_m.toFixed(0)}m` : null}
          />
          <LegendRow on={layers.dr} color={COLORS.dr} label="Dead reckoning" onClick={() => toggle('dr')} />
          <LegendRow
            on={layers.ekf}
            color={COLORS.ekf}
            label="EKF estimate"
            onClick={() => toggle('ekf')}
            value={frame ? `${frame.ekf_error_m.toFixed(1)}m` : null}
          />
          <LegendRow on={layers.ml} color={COLORS.ml} label="EKF + ML" onClick={() => toggle('ml')} />
          <div className="border-t border-navy-100 mt-1 pt-1">
            <div className="flex items-center gap-1.5 px-1.5 py-[2px]">
              <span className="inline-block h-2 w-2 rounded-full" style={{ background: COLORS.anomaly }} />
              <span className="text-2xs text-navy-700">Detected anomaly</span>
            </div>
            <div className="flex items-center gap-1.5 px-1.5 py-[2px]">
              <span className="inline-block h-1.5 w-4 rounded" style={{ background: 'rgba(93,124,177,0.35)' }} />
              <span className="text-2xs text-navy-700">GNSS outage region</span>
            </div>
            <div className="flex items-center gap-1.5 px-1.5 py-[2px]">
              <span className="inline-block h-2 w-2 rounded-full bg-emerald-600" />
              <span className="text-2xs text-navy-700">Start point</span>
            </div>
          </div>
        </div>

        {/* live readout */}
        {frame && (
          <div className="absolute top-3 right-3 z-[500] bg-white/95 backdrop-blur border border-navy-100 rounded shadow-card px-2.5 py-1.5 font-mono text-2xs text-navy-700 leading-relaxed">
            <div>
              <span className="text-navy-400">E</span> {frame.truth_lat.toFixed(6)}
            </div>
            <div>
              <span className="text-navy-400">N</span> {frame.truth_lon.toFixed(6)}
            </div>
            <div>
              <span className="text-navy-400">HDG</span> {frame.heading_deg.toFixed(0)}° ·{' '}
              <span className="text-navy-400">SPD</span> {(frame.speed_ms * 3.6).toFixed(0)} km/h
            </div>
          </div>
        )}
      </div>
    </Panel>
  )
}
