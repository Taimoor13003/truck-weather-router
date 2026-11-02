import { useCallback, useRef, useState } from 'react'
import { planTrip } from './api'
import CheckpointTable from './components/CheckpointTable'
import HeatControl from './components/HeatControl'
import MapView from './components/MapView'
import PlanForm from './components/PlanForm'
import RouteCards from './components/RouteCards'

export default function App() {
  const [plan, setPlan] = useState(null)
  const [selectedId, setSelectedId] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [hour, setHour] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [showHeat, setShowHeat] = useState(true)
  const request = useRef(null)

  const submit = useCallback(async (payload) => {
    request.current?.abort()
    const controller = new AbortController()
    request.current = controller
    setLoading(true)
    setError('')
    setPlaying(false)
    try {
      const result = await planTrip(payload, controller.signal)
      setPlan(result)
      setSelectedId(result.recommended_id)
      setHour(0)
    } catch (err) {
      if (err.name !== 'AbortError') setError(err.message || 'Something went wrong. Please try again.')
    } finally {
      if (request.current === controller) setLoading(false)
    }
  }, [])

  const selected = plan?.routes.find((r) => r.id === selectedId)

  return (
    <div className="layout">
      <aside className="sidebar">
        <header>
          <h1>Truck Weather Router</h1>
          <p>Compare routes by the weather your truck will actually meet, hour by hour.</p>
        </header>
        <PlanForm loading={loading} onSubmit={submit} />
        {error && <div className="error" role="alert">{error}</div>}
        {loading && <div className="card loading">Finding routes and checking the forecast at each checkpoint. This takes about 10 seconds.</div>}
        {plan && !loading && (
          <>
            <RouteCards plan={plan} selectedId={selectedId} onSelect={setSelectedId} />
            {selected && <CheckpointTable route={selected} interval={plan.interval_mi} timeZone={plan.timezone} />}
          </>
        )}
      </aside>
      <main className="map-wrap">
        <MapView plan={plan} selectedId={selectedId} hour={hour} showHeat={showHeat} onSelect={setSelectedId} />
        {plan && (
          <HeatControl
            departure={plan.departure}
            timeZone={plan.timezone}
            hour={hour}
            onHour={setHour}
            visible={showHeat}
            onVisible={setShowHeat}
            playing={playing}
            onPlaying={setPlaying}
          />
        )}
        {!plan && !loading && <div className="map-hint card">Enter a trip to see three routes and the weather along each.</div>}
        {loading && (
          <div className="map-loading" role="status">
            <span className="spinner" /> Planning routes…
          </div>
        )}
      </main>
    </div>
  )
}
