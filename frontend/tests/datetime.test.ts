import { describe, expect, it } from 'vitest'
import {
  localDayRange,
  minutesBetween,
  roundUpToStep,
  shiftDay,
  toLocalDate,
  toLocalInput,
} from '../app/utils/datetime'

describe('datetime helpers', () => {
  it('formats local date and datetime-local values', () => {
    const d = new Date(2026, 8, 5, 7, 3) // local time
    expect(toLocalDate(d)).toBe('2026-09-05')
    expect(toLocalInput(d)).toBe('2026-09-05T07:03')
  })

  it('rounds up to the next step and leaves aligned times alone', () => {
    expect(toLocalInput(roundUpToStep(new Date(2026, 8, 5, 13, 14), 15))).toBe('2026-09-05T13:15')
    expect(toLocalInput(roundUpToStep(new Date(2026, 8, 5, 13, 15), 15))).toBe('2026-09-05T13:15')
    expect(toLocalInput(roundUpToStep(new Date(2026, 8, 5, 13, 46, 30), 30))).toBe('2026-09-05T14:00')
  })

  it('bounds a local calendar day as [start, end)', () => {
    const { start, end } = localDayRange('2026-09-19')
    expect(new Date(start).getTime()).toBe(new Date(2026, 8, 19).getTime())
    expect(new Date(end).getTime()).toBe(new Date(2026, 8, 20).getTime())
  })

  it('shifts days across month boundaries', () => {
    expect(shiftDay('2026-09-30', 1)).toBe('2026-10-01')
    expect(shiftDay('2026-03-01', -1)).toBe('2026-02-28')
  })

  it('measures minutes between instants', () => {
    expect(minutesBetween('2026-09-19T15:00:00Z', '2026-09-19T17:00:00Z')).toBe(120)
  })
})
