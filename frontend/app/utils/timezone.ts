/**
 * A Date whose *wall-clock fields* (getHours, getDay, …) match what a clock on the wall in `timeZone`
 * would show right now — built with `Intl.DateTimeFormat`, so no timezone database needs shipping to
 * the browser. The Date's own instant (epoch ms) is meaningless; only read its local getters.
 */
export function wallClockIn(timeZone: string, at: Date = new Date()): Date {
  try {
    const parts = new Intl.DateTimeFormat('en-US', {
      timeZone, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
    }).formatToParts(at)
    const get = (type: string) => Number(parts.find(p => p.type === type)?.value ?? 0)
    // Midnight is sometimes rendered as hour 24 by this API; normalise to 0.
    return new Date(get('year'), get('month') - 1, get('day'), get('hour') % 24, get('minute'), get('second'))
  }
  catch {
    return at // an invalid/unknown timezone name: fall back to the browser's own local time
  }
}
