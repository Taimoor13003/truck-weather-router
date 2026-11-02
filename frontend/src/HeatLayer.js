import L from 'leaflet'

const LEVEL_RGB = [
  [46, 158, 91],
  [227, 181, 5],
  [240, 138, 36],
  [217, 54, 54],
  [91, 26, 107],
]
const mixRgb = (from, to, t) => from.map((c, i) => Math.round(c + (to[i] - c) * t))
const MIN_RADIUS_PX = 14
const MAX_RADIUS_PX = 70

/**
 * Canvas heatmap where colour means risk level (not point density).
 * Each checkpoint paints a soft radial blob sized to the checkpoint spacing, so neighbouring
 * blobs blend into a continuous band along the corridor. Worse levels are painted last.
 */
export default class HeatLayer extends L.Layer {
  constructor(spacingMiles) {
    super()
    this._spacingM = spacingMiles * 1609.34
    this._points = []
  }

  onAdd(map) {
    this._map = map
    this._canvas = L.DomUtil.create('canvas', 'heat-canvas leaflet-zoom-hide')
    this._canvas.style.pointerEvents = 'none'
    // Own pane, below the route lines (overlayPane is 400), so the heat never washes out the roads.
    const pane = map.getPane('heat') || map.createPane('heat')
    pane.style.zIndex = 350
    pane.appendChild(this._canvas)
    map.on('moveend zoomend resize', this._reset, this)
    this._reset()
  }

  onRemove(map) {
    map.off('moveend zoomend resize', this._reset, this)
    this._canvas.remove()
  }

  /**
   * points: [[lat, lon, levelNow, levelNext, t], ...]: the colour is blended from levelNow to
   * levelNext by t (0..1), so the map changes smoothly as the slider moves between forecast hours.
   */
  setPoints(points) {
    this._points = points
      .map(([lat, lon, a, b, t]) => ({ lat, lon, severity: a + (b - a) * t, rgb: mixRgb(LEVEL_RGB[a], LEVEL_RGB[b], t) }))
      .sort((p, q) => p.severity - q.severity)
    if (this._map) this._draw()
  }

  _reset() {
    const size = this._map.getSize()
    L.DomUtil.setPosition(this._canvas, this._map.containerPointToLayerPoint([0, 0]))
    this._canvas.width = size.x
    this._canvas.height = size.y
    this._draw()
  }

  _radiusPx(lat) {
    const metersPerPx = (40075016.686 * Math.cos((lat * Math.PI) / 180)) / (256 * 2 ** this._map.getZoom())
    return Math.min(MAX_RADIUS_PX, Math.max(MIN_RADIUS_PX, (this._spacingM * 0.65) / metersPerPx))
  }

  _draw() {
    const ctx = this._canvas.getContext('2d')
    const { width, height } = this._canvas
    ctx.clearRect(0, 0, width, height)
    for (const { lat, lon, rgb } of this._points) {
      const { x, y } = this._map.latLngToContainerPoint([lat, lon])
      const r = this._radiusPx(lat)
      if (x < -r || y < -r || x > width + r || y > height + r) continue // off screen
      const [red, green, blue] = rgb
      const gradient = ctx.createRadialGradient(x, y, 0, x, y, r)
      gradient.addColorStop(0, `rgba(${red},${green},${blue},0.8)`)
      gradient.addColorStop(0.55, `rgba(${red},${green},${blue},0.45)`)
      gradient.addColorStop(1, `rgba(${red},${green},${blue},0)`)
      ctx.fillStyle = gradient
      ctx.beginPath()
      ctx.arc(x, y, r, 0, Math.PI * 2)
      ctx.fill()
    }
  }
}
