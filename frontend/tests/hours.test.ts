import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { openStatus, parseDay, todaysHoursLabel, weeklyHoursLabels } from '../app/utils/hours'

const WEEKLY = {
  monday: '11:00-22:00', tuesday: '11:00-22:00', wednesday: '11:00-22:00', thursday: '11:00-22:00',
  friday: '11:00-23:00', saturday: '10:00-23:00', sunday: 'closed',
}

// 2026-03-02 is a Monday.
const mon = (h: number, m = 0) => new Date(2026, 2, 2, h, m)
const sun = (h: number, m = 0) => new Date(2026, 2, 1, h, m)

describe('parseDay', () => {
  it('reads a range in minutes, and closed/empty/junk as null', () => {
    expect(parseDay('11:00-22:00')).toEqual([660, 1320])
    expect(parseDay('closed')).toBeNull()
    expect(parseDay(undefined)).toBeNull()
    expect(parseDay('')).toBeNull()
    expect(parseDay('not a range')).toBeNull()
    expect(parseDay('09:00-09:00')).toBeNull()
  })
})

describe('openStatus', () => {
  it('is always open with no hours set', () => {
    expect(openStatus(null, undefined, mon(3, 0))).toEqual({ open: true })
    expect(openStatus({}, undefined, mon(3, 0))).toEqual({ open: true })
  })

  it('follows the weekly hours', () => {
    expect(openStatus(WEEKLY, undefined, mon(12, 0)).open).toBe(true)
    expect(openStatus(WEEKLY, undefined, mon(10, 59)).open).toBe(false)
    expect(openStatus(WEEKLY, undefined, sun(15, 0)).open).toBe(false)
  })

  it('reads a window crossing midnight', () => {
    const hours = { ...WEEKLY, friday: '18:00-01:00' }
    expect(openStatus(hours, undefined, new Date(2026, 2, 6, 23, 30)).open).toBe(true)   // Friday 23:30
    expect(openStatus(hours, undefined, new Date(2026, 2, 7, 0, 30)).open).toBe(true)    // Saturday 00:30, carried over
    expect(openStatus(hours, undefined, new Date(2026, 2, 7, 1, 30)).open).toBe(false)
  })

  it('a closure overrides the weekly hours, with its label', () => {
    vi.useFakeTimers()
    try {
      vi.setSystemTime(mon(12, 0))
      const result = openStatus(WEEKLY, [{ date: '2026-03-02', label: 'Private event' }])
      expect(result).toEqual({ open: false, reason: 'Private event' })
    }
    finally {
      vi.useRealTimers()
    }
  })

  it('says when it opens next when closed', () => {
    const result = openStatus(WEEKLY, undefined, sun(15, 0))
    expect(result.opensAt).toEqual({ day: 'monday', time: '11:00' })
  })
})

describe('todaysHoursLabel', () => {
  it('names todays window or says closed', () => {
    expect(todaysHoursLabel(WEEKLY, mon(9, 0))).toBe('11:00–22:00')
    expect(todaysHoursLabel(WEEKLY, sun(9, 0))).toBe('Closed today')
    expect(todaysHoursLabel(null)).toBeNull()
  })
})

describe('weeklyHoursLabels', () => {
  it('formats every day, marking the given index as today', () => {
    const rows = weeklyHoursLabels(WEEKLY, 0)
    expect(rows[0]).toEqual({ day: 'monday', label: '11:00–22:00', isToday: true })
    expect(rows[6]).toEqual({ day: 'sunday', label: 'Closed', isToday: false })
    expect(rows.every(r => r.day !== 'monday' ? !r.isToday : true)).toBe(true)
  })

  it('marks nothing as today when no index is given', () => {
    expect(weeklyHoursLabels(WEEKLY).every(r => !r.isToday)).toBe(true)
  })
})
