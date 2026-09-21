/** Rules for the kitchen screen, kept pure so they can be tested without a browser. */
import type { KitchenBoard } from '~/types/admin'
import type { Order, OrderItem } from '~/types/order'

export const STATIONS = [
  { key: 'KITCHEN', label: 'Kitchen' },
  { key: 'BAR', label: 'Bar' },
  { key: 'DESSERT', label: 'Dessert' },
] as const

/** Minutes a ticket may wait before it turns amber, then red. */
export const WARN_MINUTES = 8
export const LATE_MINUTES = 15

export type Urgency = 'ok' | 'warn' | 'late'

export function ageMs(createdAt: string, now: number): number {
  return Math.max(0, now - new Date(createdAt).getTime())
}

export function urgency(ms: number): Urgency {
  const minutes = ms / 60000
  return minutes >= LATE_MINUTES ? 'late' : minutes >= WARN_MINUTES ? 'warn' : 'ok'
}

/** 7:05, or 1:02:09 once an hour has passed. */
export function formatTimer(ms: number): string {
  const total = Math.floor(ms / 1000)
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  const pad = (n: number) => String(n).padStart(2, '0')
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`
}

export type Ticket = {
  order: Order
  /** Only the dishes this screen is responsible for. */
  items: OrderItem[]
  /** todo = something here still needs making; done = everything here is bumped. */
  state: 'todo' | 'done'
}

const isOpen = (item: OrderItem) => (item.status ?? 'NEW') !== 'READY'
const stationOf = (item: OrderItem) => item.station ?? 'KITCHEN'

/** Every ticket on the board as seen from one station (or all of them when `station` is null), oldest first. */
export function ticketsFor(board: KitchenBoard | null, station: string | null): Ticket[] {
  if (!board) return []
  return [...board.new_orders, ...board.preparing, ...board.ready]
    .map((order) => {
      const items = order.items.filter(i => station == null || stationOf(i) === station)
      return { order, items, state: items.some(isOpen) ? 'todo' as const : 'done' as const }
    })
    .filter(t => t.items.length > 0)
    .sort((a, b) => new Date(a.order.created_at).getTime() - new Date(b.order.created_at).getTime())
}

export type DayCount = { menuItemId: number, name: string, quantity: number }

/** "6× margherita open": everything still to be made across the tickets shown, biggest first. */
export function allDayCounts(tickets: Ticket[]): DayCount[] {
  const counts = new Map<number, DayCount>()
  for (const t of tickets) {
    for (const item of t.items) {
      if (!isOpen(item)) continue
      const row = counts.get(item.menu_item_id) ?? { menuItemId: item.menu_item_id, name: item.item_name, quantity: 0 }
      row.quantity += item.quantity
      counts.set(item.menu_item_id, row)
    }
  }
  return [...counts.values()].sort((a, b) => b.quantity - a.quantity || a.name.localeCompare(b.name))
}

/** Orders that appeared since the last look (for the "ding"). The first look never counts. */
export function newOrderIds(previous: Set<number> | null, tickets: Ticket[]): number[] {
  if (previous === null) return []
  return tickets.filter(t => !previous.has(t.order.id)).map(t => t.order.id)
}
