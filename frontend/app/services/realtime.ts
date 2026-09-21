import { getApiBaseUrl } from '~/services/http'
import { ACCESS_TOKEN_KEY, refreshSession } from '~/utils/session-refresh'
import type { SseStatus } from '~/utils/sse'
import { connectSse } from '~/utils/sse'

export type KitchenHandlers = {
  /** Something about the kitchen's orders changed (or we just (re)connected): refetch the board. */
  onChange: () => void
  onStatus?: (status: SseStatus) => void
}

const RELEVANT = new Set(['ready', 'order.created', 'order.status', 'resync'])

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
