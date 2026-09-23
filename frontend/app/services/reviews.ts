import type { AdminReview, EligibleVisit, PublicReviewList, Review } from '~/types/review'
import { apiFetch } from '~/services/http'

// ---- signed-in customer ---------------------------------------------------------------------

export function fetchEligibleVisits() {
  return apiFetch<EligibleVisit[]>('/api/v1/reviews/eligible')
}

export function fetchMyReviews() {
  return apiFetch<Review[]>('/api/v1/reviews')
}

export function submitReview(payload: { order_id?: number, reservation_id?: number, rating: number, comment?: string }) {
  return apiFetch<Review>('/api/v1/reviews', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

// ---- public storefront -----------------------------------------------------------------------

export function fetchPublicReviews(identifier: string, page = 1, pageSize = 10) {
  return apiFetch<PublicReviewList>(
    `/api/v1/restaurants/${encodeURIComponent(identifier)}/reviews?page=${page}&page_size=${pageSize}`,
    { auth: false },
  )
}

// ---- admin ----------------------------------------------------------------------------------

export function fetchAdminReviews(restaurantId: number) {
  return apiFetch<AdminReview[]>(`/api/v1/admin/reviews?restaurant_id=${restaurantId}`)
}

export function moderateReview(restaurantId: number, reviewId: number, isPublished: boolean) {
  return apiFetch<AdminReview>(`/api/v1/admin/reviews/${reviewId}/moderate?restaurant_id=${restaurantId}`, {
    method: 'POST',
    body: JSON.stringify({ is_published: isPublished }),
  })
}

export function replyToReview(restaurantId: number, reviewId: number, reply: string) {
  return apiFetch<AdminReview>(`/api/v1/admin/reviews/${reviewId}/reply?restaurant_id=${restaurantId}`, {
    method: 'POST',
    body: JSON.stringify({ reply }),
  })
}
