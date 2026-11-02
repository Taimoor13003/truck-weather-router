import { memo } from 'react'
import { LEVEL_COLORS, formatTime } from '../format'

export default memo(function CheckpointTable({ route, interval, timeZone }) {
  return (
    <section className="card table-card">
      <h3>
        {route.name} checkpoints <small>(every {interval} mi, weather at the truck's ETA)</small>
      </h3>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Mile</th>
              <th>ETA</th>
              <th>Wind mph</th>
              <th>Rain in/hr</th>
              <th>Snow in/hr</th>
              <th>Risk</th>
            </tr>
          </thead>
          <tbody>
            {route.checkpoints.map((c) => (
              <tr key={c.mile} title={c.reasons.join('\n')}>
                <td>{c.mile.toFixed(0)}</td>
                <td>{formatTime(c.eta, timeZone)}</td>
                <td>{c.wind_mph.toFixed(0)}</td>
                <td>{c.rain_in_hr.toFixed(2)}</td>
                <td>{c.snow_in_hr.toFixed(2)}</td>
                <td>
                  <span className="pill" style={{ background: LEVEL_COLORS[c.level] }}>{c.risk}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {route.stops.length > 0 && (
        <>
          <h3 className="stops-title">Required driver stops (US Hours of Service)</h3>
          <ul className="stops">
            {route.stops.map((s) => (
              <li key={s.start}>
                <b>{s.kind}</b> near mile {s.mile.toFixed(0)}: {formatTime(s.start, timeZone)} to {formatTime(s.end, timeZone)}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  )
})
