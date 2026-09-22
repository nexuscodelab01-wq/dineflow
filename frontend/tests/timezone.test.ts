import { describe, expect, it } from 'vitest'
import { wallClockIn } from '../app/utils/timezone'

describe('wallClockIn', () => {
  it('reads the wall-clock time of another timezone', () => {
    // 2026-06-15 18:00 UTC = 11:00 in Los Angeles (PDT, UTC-7) and 03:00 the next day in Tokyo (UTC+9).
    const at = new Date(Date.UTC(2026, 5, 15, 18, 0, 0))
    const la = wallClockIn('America/Los_Angeles', at)
    expect([la.getHours(), la.getMinutes(), la.getDate()]).toEqual([11, 0, 15])
    const tokyo = wallClockIn('Asia/Tokyo', at)
    expect([tokyo.getHours(), tokyo.getDate()]).toEqual([3, 16])
  })

  it('falls back to the given instant for an unknown timezone rather than throwing', () => {
    const at = new Date(2026, 0, 1, 10, 0, 0)
    expect(wallClockIn('Not/AZone', at).getTime()).toBe(at.getTime())
  })
})
