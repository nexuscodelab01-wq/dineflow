import type { ShiftReportRead } from '~/types/shift'
import { apiFetch } from '~/services/http'

export function fetchShifts(restaurantId: number) {
  return apiFetch<ShiftReportRead[]>(`/api/v1/admin/shifts?restaurant_id=${restaurantId}`)
}
