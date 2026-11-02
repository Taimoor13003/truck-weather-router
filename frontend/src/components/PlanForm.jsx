import { useEffect, useState } from 'react'
import { searchPlaces } from '../api'
import { defaultDeparture } from '../format'

function PlaceInput({ id, label, value, onChange, placeholder }) {
  const [options, setOptions] = useState([])
  const listId = `${id}-options`

  useEffect(() => {
    if (value.trim().length < 3) return undefined
    const controller = new AbortController()
    const timer = setTimeout(() => {
      searchPlaces(value, controller.signal)
        .then((results) => setOptions(results.map((r) => r.label)))
        .catch(() => {})
    }, 450)
    return () => {
      clearTimeout(timer)
      controller.abort()
    }
  }, [value])

  return (
    <label className="field" htmlFor={id}>
      <span>{label}</span>
      <input
        id={id}
        value={value}
        list={listId}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        autoComplete="off"
        required
      />
      <datalist id={listId}>
        {options.map((o) => (
          <option key={o} value={o} />
        ))}
      </datalist>
    </label>
  )
}

export default function PlanForm({ loading, onSubmit }) {
  const [origin, setOrigin] = useState('Dallas, TX')
  const [destination, setDestination] = useState('Chicago, IL')
  const [departure, setDeparture] = useState(defaultDeparture)
  const [weight, setWeight] = useState(45000)
  const [interval, setIntervalMi] = useState(25)

  const submit = (e) => {
    e.preventDefault()
    onSubmit({
      origin,
      destination,
      departure: new Date(departure).toISOString(),
      weight_lb: Number(weight),
      interval_mi: Number(interval),
    })
  }

  return (
    <form className="card form" onSubmit={submit}>
      <PlaceInput id="origin" label="Origin" value={origin} onChange={setOrigin} placeholder="City, state" />
      <PlaceInput id="destination" label="Destination" value={destination} onChange={setDestination} placeholder="City, state" />
      <div className="row">
        <label className="field" htmlFor="departure">
          <span>Departure</span>
          <input id="departure" type="datetime-local" value={departure} onChange={(e) => setDeparture(e.target.value)} required />
        </label>
        <label className="field" htmlFor="weight">
          <span>Load weight (lb)</span>
          <input id="weight" type="number" min="500" max="200000" step="500" value={weight} onChange={(e) => setWeight(e.target.value)} required />
        </label>
      </div>
      <label className="field" htmlFor="interval">
        <span>Weather checkpoint every</span>
        <select id="interval" value={interval} onChange={(e) => setIntervalMi(e.target.value)}>
          <option value={10}>10 miles (most detail)</option>
          <option value={25}>25 miles</option>
          <option value={50}>50 miles (fastest)</option>
        </select>
      </label>
      <button className="primary" disabled={loading}>
        {loading ? 'Forecasting weather…' : 'Plan safest route'}
      </button>
    </form>
  )
}
