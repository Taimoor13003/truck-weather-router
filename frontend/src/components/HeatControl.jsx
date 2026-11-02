import { useEffect } from 'react'
import { LEVEL_COLORS, LEVELS, addHours, formatTime } from '../format'

const MAX_HOUR = 48
const STEP_MS = 450

export default function HeatControl({ departure, hour, onHour, visible, onVisible, playing, onPlaying }) {
  // Advance one forecast hour per tick while playing, stopping at the end.
  useEffect(() => {
    if (!playing) return
    const timer = setInterval(() => {
      onHour((h) => {
        if (h >= MAX_HOUR) {
          onPlaying(false)
          return h
        }
        return h + 1
      })
    }, STEP_MS)
    return () => clearInterval(timer)
  }, [playing, onHour, onPlaying])

  return (
    <div className="heat-control card">
      <div className="heat-top">
        <label className="toggle">
          <input type="checkbox" checked={visible} onChange={(e) => onVisible(e.target.checked)} />
          Weather heatmap
        </label>
        <strong className="heat-time">
          +{hour} h · {formatTime(addHours(departure, hour))}
        </strong>
        <button
          className="play"
          onClick={() => {
            if (hour >= MAX_HOUR) onHour(0)
            onPlaying(!playing)
          }}
          aria-label={playing ? 'Pause forecast animation' : 'Play forecast animation'}
        >
          {playing ? '❚❚' : '▶'}
        </button>
      </div>
      <input
        type="range"
        min={0}
        max={MAX_HOUR}
        step={1}
        value={hour}
        onChange={(e) => {
          onPlaying(false)
          onHour(Number(e.target.value))
        }}
        aria-label="Forecast hour after departure"
      />
      <div className="legend">
        {LEVELS.map((name, i) => (
          <span key={name}>
            <i style={{ background: LEVEL_COLORS[i] }} />
            {name}
          </span>
        ))}
      </div>
    </div>
  )
}
