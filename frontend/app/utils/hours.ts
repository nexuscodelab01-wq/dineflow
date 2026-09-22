/** Opening hours: same rule as the backend (backend/app/core/hours.py), for showing "Open now" without a round trip. */

export const DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'] as const
export type Day = (typeof DAYS)[number]
export type OpeningHours = Partial<Record<Day, string>>
export type Closure = { date: string, label?: string | null }

export type OpenStatus = {
  open: boolean
  reason?: string
  /** The next opening time, in the restaurant's own local wall-clock fields (no cross-timezone math needed client-side). */
  opensAt?: { day: Day, time: string }
}

function parseClock(value: string): number | null {
  const m = /^(\d{1,2}):(\d{2})$/.exec(value.trim())
  if (!m) return null
  const h = Number(m[1])
  const min = Number(m[2])
  if (h > 23 || min > 59) return null
  return h * 60 + min
}

/** A day's value -> [openMinutes, closeMinutes], or null for closed. */
export function parseDay(value: string | undefined): [number, number] | null {
  if (!value) return null
  const text = value.trim().toLowerCase()
  if (text === '' || text === 'closed') return null
  const [a, b] = text.split('-')
  if (!a || !b) return null
  const open = parseClock(a)
  const close = parseClock(b)
  if (open === null || close === null || open === close) return null
  return [open, close]
}

function closureLabel(closures: Closure[] | undefined, isoDate: string): string | null {
  const hit = closures?.find(c => c.date === isoDate)
  return hit ? (hit.label || 'closed for the day') : null
}

/** `now` defaults to the current instant; pass one in for testing. */
export function openStatus(hours: OpeningHours | null | undefined, closures: Closure[] | undefined, now = new Date()): OpenStatus {
  if (!hours || Object.keys(hours).length === 0) return { open: true }

  const minutesOfDay = now.getHours() * 60 + now.getMinutes()
  const isoDate = now.toISOString().slice(0, 10) // caller passes a Date already shifted to local wall-clock, see useOpeningStatus
  const label = closureLabel(closures, isoDate)
  if (label) return { open: false, reason: label }

  for (const offset of [0, -1]) {
    const d = new Date(now)
    d.setDate(d.getDate() + offset)
    const dayIndex = (d.getDay() + 6) % 7 // JS: Sunday=0 -> our DAYS: Monday=0
    const window = parseDay(hours[DAYS[dayIndex]])
    if (!window) continue
    let [open, close] = window
    if (close <= open) close += 24 * 60 // crosses midnight
    const minutes = offset === 0 ? minutesOfDay : minutesOfDay + 24 * 60
    if (minutes >= open && minutes < close) return { open: true }
  }

  return { open: false, reason: 'closed right now', opensAt: nextOpen(hours, closures, now) }
}

function nextOpen(hours: OpeningHours, closures: Closure[] | undefined, now: Date): OpenStatus['opensAt'] {
  for (let offset = 0; offset < 14; offset++) {
    const d = new Date(now)
    d.setDate(d.getDate() + offset)
    if (closureLabel(closures, d.toISOString().slice(0, 10))) continue
    const dayIndex = (d.getDay() + 6) % 7
    const window = parseDay(hours[DAYS[dayIndex]])
    if (!window) continue
    const [open] = window
    if (offset > 0 || open > now.getHours() * 60 + now.getMinutes()) {
      return { day: DAYS[dayIndex], time: `${String(Math.floor(open / 60)).padStart(2, '0')}:${String(open % 60).padStart(2, '0')}` }
    }
  }
  return undefined
}

/** `hours` for today, e.g. "11:00–22:00", or "Closed today". */
export function todaysHoursLabel(hours: OpeningHours | null | undefined, now = new Date()): string | null {
  if (!hours) return null
  const dayIndex = (now.getDay() + 6) % 7
  const window = parseDay(hours[DAYS[dayIndex]])
  if (!window) return 'Closed today'
  const fmt = (m: number) => `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`
  return `${fmt(window[0])}–${fmt(window[1])}`
}
