/** Local-time helpers for reservation screens. The API speaks UTC ISO strings; people think in local time. */

const pad = (n: number) => String(n).padStart(2, '0')

/** `<input type="datetime-local">` value, e.g. 2026-09-19T19:30 */
export function toLocalInput(d: Date): string {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/** `<input type="date">` value, e.g. 2026-09-19 */
export function toLocalDate(d: Date): string {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

export function localInputToIso(value: string): string {
  return new Date(value).toISOString()
}

/** Round up to the next multiple of `stepMinutes` (never in the past). */
export function roundUpToStep(d: Date, stepMinutes = 15): Date {
  const out = new Date(d)
  out.setSeconds(0, 0)
  const remainder = out.getMinutes() % stepMinutes
  if (remainder) out.setMinutes(out.getMinutes() + (stepMinutes - remainder))
  return out
}

/** ISO instants bounding a local calendar day: [start, end). */
export function localDayRange(day: string): { start: string, end: string } {
  const start = new Date(`${day}T00:00:00`)
  const end = new Date(start)
  end.setDate(end.getDate() + 1)
  return { start: start.toISOString(), end: end.toISOString() }
}

export function shiftDay(day: string, delta: number): string {
  const d = new Date(`${day}T00:00:00`)
  d.setDate(d.getDate() + delta)
  return toLocalDate(d)
}

export function formatDayLabel(day: string): string {
  return new Date(`${day}T00:00:00`).toLocaleDateString(undefined, {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
  })
}

export function formatWhen(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

export function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })
}

export function formatTimeRange(startIso: string, endIso: string): string {
  return `${formatTime(startIso)} – ${formatTime(endIso)}`
}

export function minutesBetween(startIso: string, endIso: string): number {
  return Math.round((new Date(endIso).getTime() - new Date(startIso).getTime()) / 60000)
}
