import type { Coupon, CouponCreatePayload, CouponPreview } from '~/types/coupon'
import { apiFetch } from '~/services/http'

// ---- signed-in customer ---------------------------------------------------------------------

/** What a code is worth against the current cart. Advisory: the order endpoint decides for real. */
export function previewCoupon(code: string, subtotal: number) {
  return apiFetch<CouponPreview>('/api/v1/coupons/preview', {
    method: 'POST',
    body: JSON.stringify({ code, subtotal: subtotal.toFixed(2) }),
  })
}

// ---- admin ----------------------------------------------------------------------------------

export function fetchCoupons(restaurantId: number) {
  return apiFetch<Coupon[]>(`/api/v1/admin/coupons?restaurant_id=${restaurantId}`)
}

export function createCoupon(restaurantId: number, payload: CouponCreatePayload) {
  return apiFetch<Coupon>(`/api/v1/admin/coupons?restaurant_id=${restaurantId}`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateCoupon(restaurantId: number, couponId: number, payload: Partial<Coupon>) {
  return apiFetch<Coupon>(`/api/v1/admin/coupons/${couponId}?restaurant_id=${restaurantId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export function deleteCoupon(restaurantId: number, couponId: number) {
  return apiFetch<void>(`/api/v1/admin/coupons/${couponId}?restaurant_id=${restaurantId}`, {
    method: 'DELETE',
  })
}
