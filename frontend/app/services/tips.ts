import type { TipAllocation, TipReport } from '~/types/tips'
import { apiFetch } from '~/services/http'

export function fetchTipReport(restaurantId: number, start: string, end: string) {
  const params = new URLSearchParams({ restaurant_id: String(restaurantId), start, end })
  return apiFetch<TipReport>(`/api/v1/admin/tips/report?${params}`)
}

/** Writes the period into the tip ledger. Refused if any of it was already finalized. */
export function finalizeTips(restaurantId: number, start: string, end: string) {
  return apiFetch<TipReport>(`/api/v1/admin/tips/finalize?restaurant_id=${restaurantId}`, {
    method: 'POST',
    body: JSON.stringify({ start, end }),
  })
}

export function fetchTipHistory(restaurantId: number) {
  return apiFetch<TipAllocation[]>(`/api/v1/admin/tips/history?restaurant_id=${restaurantId}`)
}

/** Push the tip settings to Stripe so the card reader shows (or hides) the tip screen. */
export function syncTerminalTipping(restaurantId: number) {
  return apiFetch<{ location_id: string | null, configuration_id: string | null, tipping: boolean }>(
    `/api/v1/admin/settings/terminal/sync?restaurant_id=${restaurantId}`,
    { method: 'POST' },
  )
}
