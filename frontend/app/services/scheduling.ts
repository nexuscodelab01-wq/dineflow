import type { PickupSlots } from '~/types/scheduling'
import { apiFetch } from '~/services/http'

/** Collection times still bookable on `date` (YYYY-MM-DD, the restaurant's local day). */
export function fetchPickupSlots(identifier: string, date?: string) {
  const query = date ? `?on=${encodeURIComponent(date)}` : ''
  return apiFetch<PickupSlots>(`/api/v1/restaurants/${encodeURIComponent(identifier)}/pickup-slots${query}`, {
    auth: false,
  })
}
