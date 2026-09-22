import type {
  AdminAvailabilityResponse,
  AvailabilityResponse,
  CreateReservationPayload,
  Reservation,
  ReservationStatus,
  UpdateReservationPayload,
} from '~/types/reservation'
import { apiFetch } from '~/services/http'

export function fetchReservationAvailability(
  identifier: string | number,
  params: { starts_at: string; party_size: number; duration_minutes?: number },
) {
  const search = new URLSearchParams({
    starts_at: params.starts_at,
    party_size: String(params.party_size),
  })
  if (params.duration_minutes) search.set('duration_minutes', String(params.duration_minutes))
  return apiFetch<AvailabilityResponse>(
    `/api/v1/restaurants/${identifier}/reservations/availability?${search}`,
    { auth: false },
  )
}

export function createReservation(identifier: string | number, payload: CreateReservationPayload) {
  return apiFetch<Reservation>(`/api/v1/restaurants/${identifier}/reservations`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function fetchMyReservations(restaurantId?: number, includePast = false) {
  const params = new URLSearchParams()
  if (restaurantId) params.set('restaurant_id', String(restaurantId))
  if (includePast) params.set('include_past', 'true')
  const q = params.toString()
  return apiFetch<Reservation[]>(`/api/v1/reservations/me${q ? `?${q}` : ''}`)
}

export function cancelReservation(reservationId: number) {
  return apiFetch<Reservation>(`/api/v1/reservations/${reservationId}/cancel`, {
    method: 'POST',
  })
}

export function confirmReservationHold(reservationId: number) {
  return apiFetch<Reservation>(`/api/v1/reservations/${reservationId}/confirm`, {
    method: 'POST',
  })
}

/** Bookings starting in [start, end) — pass local-day bounds as ISO strings. */
export function fetchAdminReservations(restaurantId: number, range: { start?: string, end?: string } = {}) {
  const params = new URLSearchParams({ restaurant_id: String(restaurantId) })
  if (range.start) params.set('start', range.start)
  if (range.end) params.set('end', range.end)
  return apiFetch<Reservation[]>(`/api/v1/admin/reservations?${params}`)
}

/** Per-table status for the requested slot. `excludeReservationId` ignores the booking being edited. */
export function fetchAdminAvailability(
  restaurantId: number,
  params: { starts_at: string, party_size: number, duration_minutes: number, exclude_reservation_id?: number },
) {
  const search = new URLSearchParams({
    restaurant_id: String(restaurantId),
    starts_at: params.starts_at,
    party_size: String(params.party_size),
    duration_minutes: String(params.duration_minutes),
  })
  if (params.exclude_reservation_id) search.set('exclude_reservation_id', String(params.exclude_reservation_id))
  return apiFetch<AdminAvailabilityResponse>(`/api/v1/admin/reservations/availability?${search}`)
}

export function updateAdminReservation(
  restaurantId: number,
  reservationId: number,
  payload: UpdateReservationPayload,
) {
  return apiFetch<Reservation>(
    `/api/v1/admin/reservations/${reservationId}?restaurant_id=${restaurantId}`,
    {
      method: 'PATCH',
      body: JSON.stringify(payload),
    },
  )
}

export function createAdminReservation(
  restaurantId: number,
  payload: CreateReservationPayload & { seat_immediately?: boolean },
) {
  return apiFetch<Reservation>(
    `/api/v1/admin/reservations?restaurant_id=${restaurantId}`,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
  )
}

/** Give seated guests more time; the API refuses if the next booking would clash. */
export function extendAdminReservation(restaurantId: number, reservationId: number, minutes: number) {
  return apiFetch<Reservation>(
    `/api/v1/admin/reservations/${reservationId}/extend?restaurant_id=${restaurantId}`,
    {
      method: 'POST',
      body: JSON.stringify({ minutes }),
    },
  )
}

export function updateAdminReservationStatus(
  restaurantId: number,
  reservationId: number,
  status: ReservationStatus,
  notes?: string,
) {
  return apiFetch<Reservation>(
    `/api/v1/admin/reservations/${reservationId}/status?restaurant_id=${restaurantId}`,
    {
      method: 'PATCH',
      body: JSON.stringify({ status, notes }),
    },
  )
}

// ---- acting from an emailed link (no account) -------------------------------------------------

export function fetchReservationByActionToken(token: string) {
  return apiFetch<Reservation>(`/api/v1/reservations/actions/${encodeURIComponent(token)}`, { auth: false })
}

export function confirmReservationByActionToken(token: string) {
  return apiFetch<Reservation>(`/api/v1/reservations/actions/${encodeURIComponent(token)}/confirm`, {
    method: 'POST',
    auth: false,
  })
}

export function cancelReservationByActionToken(token: string) {
  return apiFetch<Reservation>(`/api/v1/reservations/actions/${encodeURIComponent(token)}/cancel`, {
    method: 'POST',
    auth: false,
  })
}
