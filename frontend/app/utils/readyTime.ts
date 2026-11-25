/** The "ready in …" estimate staff give a customer, kept pure so it can be tested without a browser. */
import type { Order } from '~/types/order'

/** One-tap choices on the kitchen screen, in minutes. */
export const READY_CHOICES = [10, 15, 20, 30, 45, 60, 90, 120] as const

/** 15 → "15 min", 60 → "1 h", 90 → "1 h 30". */
export function formatMinutes(minutes: number): string {
  const m = Math.round(minutes)
  if (m < 60) return `${m} min`
  const h = Math.floor(m / 60)
  const rest = m % 60
  return rest ? `${h} h ${rest}` : `${h} h`
}

/** Only pickup and delivery have a wait to promise, and only while the order is still being made. */
export function canSetReadyTime(order: Pick<Order, 'order_type' | 'status'>): boolean {
  return (order.order_type === 'PICKUP' || order.order_type === 'DELIVERY')
    && (order.status === 'CONFIRMED' || order.status === 'PREPARING')
}

/** The promise to show, or null when none was made (or the order is already past that stage). */
export function readyEstimate(order: Pick<Order, 'estimated_ready_at' | 'status'>, now: number = Date.now()): { at: string, minutesLeft: number } | null {
  if (!order.estimated_ready_at) return null
  if (order.status !== 'CONFIRMED' && order.status !== 'PREPARING') return null
  const at = new Date(order.estimated_ready_at)
  return {
    at: at.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }),
    minutesLeft: Math.round((at.getTime() - now) / 60000),
  }
}

/** "Ready around 7:45 pm", or "Taking a little longer than planned" once the promised time has passed. */
export function readyLabel(order: Pick<Order, 'order_type' | 'estimated_ready_at' | 'status'>, now: number = Date.now()): string | null {
  const est = readyEstimate(order, now)
  if (!est) return null
  if (est.minutesLeft < -2) return 'Taking a little longer than planned'
  return `${order.order_type === 'DELIVERY' ? 'Arriving around' : 'Ready around'} ${est.at}`
}
