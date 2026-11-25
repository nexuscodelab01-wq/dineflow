import type { OrderType } from '~/types/order'

interface Offering { pickup_enabled: boolean, delivery_enabled: boolean, dine_in_enabled: boolean }

/** The kinds of order a restaurant takes online: only what it has switched on (dine-in also needs reservations). */
export function availableOrderTypes(r: Offering | null | undefined, reservationsOn: boolean): OrderType[] {
  const types: OrderType[] = []
  if (!r || r.pickup_enabled) types.push('PICKUP')
  if (!r || r.delivery_enabled) types.push('DELIVERY')
  if (reservationsOn && (!r || r.dine_in_enabled)) types.push('DINE_IN')
  return types
}
