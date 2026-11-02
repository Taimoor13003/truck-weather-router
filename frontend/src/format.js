export const LEVELS = ['Low', 'Moderate', 'High', 'Severe', 'No Travel']
export const LEVEL_COLORS = ['#2e9e5b', '#e3b505', '#f08a24', '#d93636', '#5b1a6b']
export const ROUTE_COLORS = ['#2563eb', '#7c3aed', '#0891b2']

export function formatDuration(seconds) {
  const minutes = Math.round(seconds / 60)
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  return h ? `${h} h ${String(m).padStart(2, '0')} min` : `${m} min`
}

const formatters = new Map()

/** "Tue 1:35 PM CST": times are shown in the origin's time zone so the whole trip reads on one clock. */
export function formatTime(iso, timeZone) {
  if (!formatters.has(timeZone)) {
    formatters.set(
      timeZone,
      new Intl.DateTimeFormat('en-US', { weekday: 'short', hour: 'numeric', minute: '2-digit', timeZoneName: 'short', timeZone }),
    )
  }
  return formatters.get(timeZone).format(new Date(iso))
}

export function formatOffset(hours) {
  const whole = Math.floor(hours)
  const minutes = Math.round((hours - whole) * 60)
  return minutes ? `+${whole} h ${minutes} min` : `+${whole} h`
}

export function addHours(iso, hours) {
  return new Date(new Date(iso).getTime() + hours * 3_600_000).toISOString()
}

/** Default departure: the next quarter hour, at least 30 minutes away, as a datetime-local value. */
export function defaultDeparture() {
  const d = new Date(Date.now() + 30 * 60_000)
  d.setMinutes(Math.ceil(d.getMinutes() / 15) * 15, 0, 0)
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}
