import type { Adjustment } from '~/types/adjustment'
import { apiFetch } from '~/services/http'

export function fetchAdjustments(restaurantId: number, start: string, end: string) {
  const params = new URLSearchParams({ restaurant_id: String(restaurantId), start, end })
  return apiFetch<Adjustment[]>(`/api/v1/admin/adjustments?${params}`)
}
