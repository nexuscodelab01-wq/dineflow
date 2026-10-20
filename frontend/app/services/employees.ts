import type { DateRangePreset } from '~/types/analytics'
import type { EmployeeReportRow } from '~/types/shift'
import { apiFetch } from '~/services/http'

export function fetchEmployeeReport(
  restaurantId: number,
  range: DateRangePreset = 'last_7_days',
  startDate?: string,
  endDate?: string,
) {
  const params = new URLSearchParams({ restaurant_id: String(restaurantId), range })
  if (range === 'custom' && startDate && endDate) {
    params.set('start_date', startDate)
    params.set('end_date', endDate)
  }
  return apiFetch<EmployeeReportRow[]>(`/api/v1/admin/analytics/employees?${params}`)
}
