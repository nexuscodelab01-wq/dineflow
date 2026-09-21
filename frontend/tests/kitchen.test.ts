import { describe, expect, it } from 'vitest'
import type { KitchenBoard } from '../app/types/admin'
import type { Order, OrderItem } from '../app/types/order'
import { allDayCounts, ageMs, formatTimer, LATE_MINUTES, newOrderIds, ticketsFor, urgency, WARN_MINUTES } from '../app/utils/kitchen'

const item = (id: number, menuItemId: number, name: string, quantity: number, station: string, status: 'NEW' | 'READY' = 'NEW'): OrderItem => ({
  id, menu_item_id: menuItemId, item_name: name, quantity, unit_price: '1', line_total: '1', station, status, modifiers: [],
})
const order = (id: number, createdAt: string, items: OrderItem[]): Order => ({ id, created_at: createdAt, items } as unknown as Order)

const board = (orders: Order[]): KitchenBoard => ({ new_orders: orders, preparing: [], ready: [] })

describe('timers', () => {
  it('turns amber then red as a ticket waits', () => {
    expect(urgency(0)).toBe('ok')
    expect(urgency((WARN_MINUTES - 0.1) * 60000)).toBe('ok')
    expect(urgency(WARN_MINUTES * 60000)).toBe('warn')
    expect(urgency(LATE_MINUTES * 60000)).toBe('late')
  })

  it('formats minutes and seconds, and hours when needed', () => {
    expect(formatTimer(0)).toBe('0:00')
    expect(formatTimer(65_000)).toBe('1:05')
    expect(formatTimer(3_725_000)).toBe('1:02:05')
  })

  it('never shows a negative age (clock drift)', () => {
    expect(ageMs('2030-01-01T00:00:00Z', new Date('2029-01-01T00:00:00Z').getTime())).toBe(0)
  })
})

describe('tickets per station', () => {
  const o1 = order(1, '2026-01-01T10:00:00Z', [item(1, 10, 'Burger', 1, 'KITCHEN'), item(2, 20, 'Lemonade', 2, 'BAR')])
  const o2 = order(2, '2026-01-01T09:00:00Z', [item(3, 20, 'Lemonade', 1, 'BAR', 'READY')])
  const b = board([o1, o2])

  it('shows every dish on the all-stations view, oldest ticket first', () => {
    const tickets = ticketsFor(b, null)
    expect(tickets.map(t => t.order.id)).toEqual([2, 1])
    expect(tickets[1]!.items).toHaveLength(2)
  })

  it('shows a station only its own dishes and drops tickets with none', () => {
    const bar = ticketsFor(b, 'BAR')
    expect(bar.map(t => [t.order.id, t.items.map(i => i.item_name)])).toEqual([[2, ['Lemonade']], [1, ['Lemonade']]])
    expect(ticketsFor(b, 'DESSERT')).toEqual([])
    expect(ticketsFor(b, 'KITCHEN').map(t => t.order.id)).toEqual([1])
  })

  it('marks a ticket done for a station once all its dishes there are bumped', () => {
    expect(ticketsFor(b, 'BAR').map(t => t.state)).toEqual(['done', 'todo'])
    expect(ticketsFor(b, null).map(t => t.state)).toEqual(['done', 'todo'])
  })

  it('treats items without a station or status as new kitchen dishes (older data)', () => {
    const legacy = { id: 9, menu_item_id: 1, item_name: 'Old', quantity: 1, modifiers: [] } as unknown as OrderItem
    const [t] = ticketsFor(board([order(5, '2026-01-01T10:00:00Z', [legacy])]), 'KITCHEN')
    expect(t!.state).toBe('todo')
  })

  it('handles no board yet', () => {
    expect(ticketsFor(null, null)).toEqual([])
  })
})

describe('all-day counts', () => {
  it('adds up what is still to be made, biggest first, ignoring bumped dishes', () => {
    const tickets = ticketsFor(board([
      order(1, '2026-01-01T10:00:00Z', [item(1, 10, 'Margherita', 2, 'KITCHEN'), item(2, 11, 'Pepperoni', 1, 'KITCHEN')]),
      order(2, '2026-01-01T10:01:00Z', [item(3, 10, 'Margherita', 4, 'KITCHEN'), item(4, 11, 'Pepperoni', 3, 'KITCHEN', 'READY')]),
    ]), null)
    expect(allDayCounts(tickets)).toEqual([
      { menuItemId: 10, name: 'Margherita', quantity: 6 },
      { menuItemId: 11, name: 'Pepperoni', quantity: 1 },
    ])
  })
})

describe('new ticket detection', () => {
  const tickets = ticketsFor(board([order(1, '2026-01-01T10:00:00Z', [item(1, 1, 'A', 1, 'KITCHEN')]), order(2, '2026-01-01T10:01:00Z', [item(2, 1, 'A', 1, 'KITCHEN')])]), null)

  it('does not ding for what was already there when the screen opened', () => {
    expect(newOrderIds(null, tickets)).toEqual([])
  })

  it('dings only for orders not seen before', () => {
    expect(newOrderIds(new Set([1]), tickets)).toEqual([2])
    expect(newOrderIds(new Set([1, 2]), tickets)).toEqual([])
  })
})
