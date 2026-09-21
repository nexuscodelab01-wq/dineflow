import { getApiBaseUrl } from '~/services/http'
import { ACCESS_TOKEN_KEY, refreshSession } from '~/utils/session-refresh'
import type { SseStatus } from '~/utils/sse'
import { connectSse } from '~/utils/sse'

export type KitchenHandlers = {
  /** Something about the kitchen's orders changed (or we just (re)connected): refetch the board. */
  onChange: () => void
  onStatus?: (status: SseStatus) => void
}

const RELEVANT = new Set(['ready', 'order.created', 'order.status', 'resync', 'request.created', 'request.done', 'session.closed', 'ticket.updated', 'menu.changed'])

/** Live updates for one restaurant's kitchen screen. Returns a handle; call close() when leaving. */
export function subscribeKitchen(restaurantId: number, handlers: KitchenHandlers) {
  const base = getApiBaseUrl()
  return connectSse({
    url: `${base}/api/v1/admin/kitchen/stream?restaurant_id=${restaurantId}`,
    getToken: () => localStorage.getItem(ACCESS_TOKEN_KEY),
    onAuthExpired: () => refreshSession({ baseUrl: base, storage: localStorage }),
    onStatus: handlers.onStatus,
    onEvent: (type) => {
      if (RELEVANT.has(type)) handlers.onChange()
    },
  })
}

export type LiveHandlers = {
  /** Something about this order / table changed (or we just (re)connected): refetch it. */
  onChange: () => void
  onStatus?: (status: SseStatus) => void
}

/** Live status for one of the signed-in customer's orders. */
export function subscribeOrder(orderId: number, handlers: LiveHandlers) {
  const base = getApiBaseUrl()
  return connectSse({
    url: `${base}/api/v1/orders/${orderId}/stream`,
    getToken: () => localStorage.getItem(ACCESS_TOKEN_KEY),
    onAuthExpired: () => refreshSession({ baseUrl: base, storage: localStorage }),
    onStatus: handlers.onStatus,
    onEvent: (type) => {
      if (type === 'ready' || type === 'order.status' || type === 'resync') handlers.onChange()
    },
  })
}

/** Live updates for a table's shared tab, using the device's table pass (not an account). */
export function subscribeTableSession(passToken: string, handlers: LiveHandlers) {
  return connectSse({
    url: `${getApiBaseUrl()}/api/v1/table-session/stream`,
    getToken: () => passToken,
    onStatus: handlers.onStatus,
    onEvent: (type) => {
      if (['ready', 'round.created', 'order.status', 'session.closed', 'request.created', 'request.done', 'resync'].includes(type)) handlers.onChange()
    },
  })
}
