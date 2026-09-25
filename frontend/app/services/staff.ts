import type { StaffInvitePayload, StaffInviteResult, StaffMember } from '~/types/staff'
import { apiFetch } from '~/services/http'

export function fetchStaff(restaurantId: number) {
  return apiFetch<StaffMember[]>(`/api/v1/admin/staff?restaurant_id=${restaurantId}`)
}

export function inviteStaff(restaurantId: number, payload: StaffInvitePayload) {
  return apiFetch<StaffInviteResult>(`/api/v1/admin/staff?restaurant_id=${restaurantId}`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateStaff(restaurantId: number, membershipId: number, payload: { role?: string, is_active?: boolean }) {
  return apiFetch<StaffMember>(`/api/v1/admin/staff/${membershipId}?restaurant_id=${restaurantId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export function resendStaffInvite(restaurantId: number, membershipId: number) {
  return apiFetch<{ invite_link: string }>(`/api/v1/admin/staff/${membershipId}/resend-invite?restaurant_id=${restaurantId}`, {
    method: 'POST',
  })
}
