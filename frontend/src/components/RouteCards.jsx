import { LEVEL_COLORS, LEVELS, ROUTE_COLORS, formatDuration, formatTime } from '../format'

/** Horizontal bar: the route's length split by the risk level of each stretch. */
function RiskBar({ checkpoints }) {
  const total = checkpoints[checkpoints.length - 1].mile || 1
  const stretches = checkpoints.slice(0, -1).map((c, i) => ({
    level: Math.max(c.level, checkpoints[i + 1].level),
    width: ((checkpoints[i + 1].mile - c.mile) / total) * 100,
    key: c.mile,
  }))
  return (
    <div className="riskbar" role="img" aria-label="Risk along the route">
      {stretches.map((s) => (
        <span key={s.key} style={{ width: `${s.width}%`, background: LEVEL_COLORS[s.level] }} />
      ))}
    </div>
  )
}

export default function RouteCards({ plan, selectedId, onSelect }) {
  return (
    <section className="routes" aria-label="Route options">
      <p className="recommendation">
        <strong>Recommended:</strong> {plan.recommendation}
      </p>
      {plan.routes.map((route, i) => {
        const recommended = route.id === plan.recommended_id
        const s = route.summary
        return (
          <button
            key={route.id}
            className={`card route ${selectedId === route.id ? 'selected' : ''}`}
            style={{ '--route-color': ROUTE_COLORS[i] }}
            onClick={() => onSelect(route.id)}
          >
            <div className="route-head">
              <span className="swatch" />
              <strong>{route.name}</strong>
              {recommended && <span className="badge good">Recommended</span>}
              {route.blocked && <span className="badge bad">No Travel zone</span>}
              <span className="rank">#{route.rank} by safety</span>
            </div>
            <div className="route-stats">
              <span>{route.distance_mi.toFixed(0)} mi</span>
              <span>{formatDuration(route.duration_s)}</span>
              <span>arrive {formatTime(route.arrival)}</span>
            </div>
            <RiskBar checkpoints={route.checkpoints} />
            <div className="route-risk">
              <span>Worst: <b style={{ color: LEVEL_COLORS[s.max_level] }}>{LEVELS[s.max_level]}</b></span>
              <span>Severe+ {s.severe_miles.toFixed(0)} mi</span>
              <span>High {s.high_miles.toFixed(0)} mi</span>
              <span>Avg risk {s.avg_risk.toFixed(2)}</span>
            </div>
          </button>
        )
      })}
    </section>
  )
}
