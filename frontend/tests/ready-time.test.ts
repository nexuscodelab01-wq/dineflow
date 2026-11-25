import { describe, expect, it } from 'vitest'
import { canSetReadyTime, formatMinutes, readyEstimate, readyLabel } from '../app/utils/readyTime'

const now = new Date('2026-11-25T18:00:00Z').getTime()
const at = (min: number) => new Date(now + min * 60000).toISOString()

describe('formatMinutes', () => {
  it('reads like people say it', () => {
    expect(formatMinutes(15)).toBe('15 min')
    expect(formatMinutes(60)).toBe('1 h')
    expect(formatMinutes(90)).toBe('1 h 30')
    expect(formatMinutes(125)).toBe('2 h 5')
  })
})

describe('canSetReadyTime', () => {
  it('only applies to pickup and delivery while being made', () => {
    expect(canSetReadyTime({ order_type: 'PICKUP', status: 'CONFIRMED' })).toBe(true)
    expect(canSetReadyTime({ order_type: 'DELIVERY', status: 'PREPARING' })).toBe(true)
    expect(canSetReadyTime({ order_type: 'DINE_IN', status: 'PREPARING' })).toBe(false)
    expect(canSetReadyTime({ order_type: 'PICKUP', status: 'READY' })).toBe(false)
    expect(canSetReadyTime({ order_type: 'PICKUP', status: 'PENDING' })).toBe(false)
  })
})

describe('readyEstimate / readyLabel', () => {
  it('is empty when staff never set a time', () => {
    expect(readyEstimate({ estimated_ready_at: null, status: 'PREPARING' }, now)).toBeNull()
  })
  it('stops once the order is ready', () => {
    expect(readyEstimate({ estimated_ready_at: at(30), status: 'READY' }, now)).toBeNull()
  })
  it('counts the minutes left', () => {
    expect(readyEstimate({ estimated_ready_at: at(30), status: 'PREPARING' }, now)?.minutesLeft).toBe(30)
  })
  it('says arriving for delivery and ready for pickup', () => {
    expect(readyLabel({ order_type: 'PICKUP', estimated_ready_at: at(30), status: 'PREPARING' }, now)).toMatch(/^Ready around /)
    expect(readyLabel({ order_type: 'DELIVERY', estimated_ready_at: at(30), status: 'PREPARING' }, now)).toMatch(/^Arriving around /)
  })
  it('admits when the promise has passed', () => {
    expect(readyLabel({ order_type: 'PICKUP', estimated_ready_at: at(-10), status: 'PREPARING' }, now)).toBe('Taking a little longer than planned')
  })
})
