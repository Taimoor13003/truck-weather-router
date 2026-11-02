import { useEffect, useRef } from 'react'
import HeatLayer from '../HeatLayer'
import L from '../leaflet'
import { LEVEL_COLORS, LEVELS, ROUTE_COLORS, formatOffset, formatTime } from '../format'

const endpointIcon = (text, color) =>
  L.divIcon({
    className: '',
    html: `<div class="endpoint" style="background:${color}">${text}</div>`,
    iconSize: [26, 26],
    iconAnchor: [13, 13],
  })

const stopIcon = (text, rest) =>
  L.divIcon({
    className: '',
    html: `<div class="stop-marker ${rest ? 'rest' : ''}">${text}</div>`,
    iconSize: [20, 20],
    iconAnchor: [10, 10],
  })

const popupHtml = (c, hour, timeZone) => {
  const nearest = Math.round(hour)
  return `
  <div class="popup">
    <b>Mile ${c.mile.toFixed(0)}</b> · ETA ${formatTime(c.eta, timeZone)}<br/>
    Wind ${c.wind_mph.toFixed(0)} mph · Rain ${c.rain_in_hr.toFixed(2)} in/hr · Snow ${c.snow_in_hr.toFixed(2)} in/hr<br/>
    <span class="pill" style="background:${LEVEL_COLORS[c.level]}">${c.risk}</span>
    ${c.reasons.map((r) => `<div>${r}</div>`).join('')}
    <div class="muted">Heatmap at ${formatOffset(nearest)}: ${LEVELS[c.heat[nearest]]}</div>
  </div>`
}

export default function MapView({ plan, selectedId, hour, showHeat, onSelect }) {
  const containerRef = useRef(null)
  const mapRef = useRef(null)
  const routeLayer = useRef(null)
  const heatLayer = useRef(null)
  const fittedFor = useRef(null)
  const hourRef = useRef(hour)
  useEffect(() => {
    hourRef.current = hour
  }, [hour])

  useEffect(() => {
    const map = L.map(containerRef.current, { zoomControl: true, preferCanvas: true }).setView([39, -97], 4)
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 18,
      attribution: '&copy; OpenStreetMap contributors',
    }).addTo(map)
    routeLayer.current = L.layerGroup().addTo(map)
    mapRef.current = map
    return () => map.remove()
  }, [])

  // Routes, checkpoints and end markers: redrawn when the plan or selection changes (not per slider tick).
  useEffect(() => {
    const group = routeLayer.current
    group.clearLayers()
    if (!plan) return

    // Draw the selected route last so it sits on top.
    const ordered = [...plan.routes].sort((a, b) => (a.id === selectedId) - (b.id === selectedId))
    for (const route of ordered) {
      const index = plan.routes.indexOf(route)
      const selected = route.id === selectedId
      const line = L.polyline(route.geometry, {
        color: ROUTE_COLORS[index],
        weight: selected ? 6 : 4,
        opacity: selected ? 0.95 : 0.45,
        dashArray: route.blocked ? '8 8' : null,
      })
      line.on('click', () => onSelect(route.id))
      line.bindTooltip(`${route.name}: ${route.distance_mi.toFixed(0)} mi`, { sticky: true })
      group.addLayer(line)

      for (const c of route.checkpoints) {
        const marker = L.circleMarker([c.lat, c.lon], {
          radius: selected ? 7 : 4,
          color: '#fff',
          weight: selected ? 2 : 1,
          fillColor: LEVEL_COLORS[c.level],
          fillOpacity: selected ? 1 : 0.6,
        })
        if (selected) marker.bindPopup(() => popupHtml(c, hourRef.current, plan.timezone))
        group.addLayer(marker)
      }
      if (selected) {
        for (const s of route.stops) {
          const rest = s.kind === '10-h rest'
          const stop = L.marker([s.lat, s.lon], { icon: stopIcon(rest ? 'R' : 'B', rest), zIndexOffset: 500 })
          const when = `${formatTime(s.start, plan.timezone)} to ${formatTime(s.end, plan.timezone)}`
          stop.bindTooltip(`${s.kind} · mile ${s.mile.toFixed(0)} · ${when}`)
          group.addLayer(stop)
        }
      }
    }
    const first = plan.routes[0].geometry
    group.addLayer(L.marker(first[0], { icon: endpointIcon('A', '#111827') }))
    group.addLayer(L.marker(first[first.length - 1], { icon: endpointIcon('B', '#111827') }))
  }, [plan, selectedId, onSelect])

  // Heatmap layer exists while a plan is shown and the toggle is on.
  useEffect(() => {
    const map = mapRef.current
    if (!plan || !showHeat) return
    const layer = new HeatLayer(plan.interval_mi).addTo(map)
    heatLayer.current = layer
    return () => {
      map.removeLayer(layer)
      heatLayer.current = null
    }
  }, [plan, showHeat])

  // Slider: recolour every checkpoint of every route with the forecast `hour` hours after departure.
  // `hour` can be fractional (the slider moves in 15-minute steps); colours blend between whole hours.
  useEffect(() => {
    if (!plan || !heatLayer.current) return
    const h0 = Math.floor(hour)
    const h1 = Math.min(h0 + 1, plan.routes[0].checkpoints[0].heat.length - 1)
    const t = hour - h0
    heatLayer.current.setPoints(
      plan.routes.flatMap((r) => r.checkpoints.map((c) => [c.lat, c.lon, c.heat[h0], c.heat[h1], t])),
    )
  }, [plan, showHeat, hour])

  // Zoom to the new trip once per plan, not on every slider tick.
  useEffect(() => {
    if (!plan || fittedFor.current === plan) return
    fittedFor.current = plan
    const bounds = L.latLngBounds(plan.routes.flatMap((r) => r.geometry))
    mapRef.current.fitBounds(bounds, { padding: [40, 40] })
  }, [plan])

  return <div ref={containerRef} className="map" />
}
