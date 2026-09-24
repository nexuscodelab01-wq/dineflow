import type { AdminLoyaltyAccount, LoyaltyAccount } from '~/types/loyalty'
import { apiFetch } from '~/services/http'

// ---- signed-in customer ---------------------------------------------------------------------

export function fetchMyLoyaltyAccount() {
  return apiFetch<LoyaltyAccount>('/api/v1/loyalty')
}

// ---- admin ----------------------------------------------------------------------------------

export function fetchAdminLoyaltyAccounts(restaurantId: number) {
  return apiFetch<AdminLoyaltyAccount[]>(`/api/v1/admin/loyalty?restaurant_id=${restaurantId}`)
}

export function adjustLoyaltyPoints(restaurantId: number, userId: number, points: number, note?: string) {
  return apiFetch<AdminLoyaltyAccount>(`/api/v1/admin/loyalty/${userId}/adjust?restaurant_id=${restaurantId}`, {
    method: 'POST',
    body: JSON.stringify({ points, note: note || undefined }),
  })
}
