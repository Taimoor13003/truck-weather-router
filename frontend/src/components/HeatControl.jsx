import { useEffect } from 'react'
import { LEVEL_COLORS, LEVELS, addHours, formatOffset, formatTime } from '../format'

const MAX_HOUR = 48
const STEP_HOURS = 0.25 // 15-minute steps; the heat layer blends colours between whole hours
const TICK_MS = 120 // full 48 h animation in about 23 seconds

export default function HeatControl({ departure, timeZone, hour, onHour, visible, onVisible, playing, onPlaying }) {
  // While playing, advance one step per tick.
  useEffect(() => {
    if (!playing) return undefined
    const timer = setInterval(() => onHour((h) => Math.min(MAX_HOUR, h + STEP_HOURS)), TICK_MS)
    return () => clearInterval(timer)
  }, [playing, onHour])

  // Stop at the end of the forecast window.
  useEffect(() => {
    if (playing && hour >= MAX_HOUR) onPlaying(false)
  }, [playing, hour, onPlaying])

  return (
    <div className="heat-control card">
      <div className="heat-top">
        <label className="toggle">
          <input type="checkbox" checked={visible} onChange={(e) => onVisible(e.target.checked)} />
          Weather heatmap
        </label>
        <strong className="heat-time">
          {formatOffset(hour)} · {formatTime(addHours(departure, hour), timeZone)}
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
        step={STEP_HOURS}
        value={hour}
        onChange={(e) => {
          onPlaying(false)
          onHour(Number(e.target.value))
        }}
        aria-label="Hours after departure shown on the heatmap"
        aria-valuetext={`${formatOffset(hour)} after departure`}
      />
      <div className="legend">
        {LEVELS.map((name, i) => (
          <span key={name}>
            <i style={{ background: LEVEL_COLORS[i] }} />
            {name}
          </span>
        ))}
        <span className="legend-note">Risk if driving there at that hour</span>
      </div>
    </div>
  )
}
