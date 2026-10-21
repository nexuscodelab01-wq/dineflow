import type { DeviceKind, DevicePairResult, PosDevice } from '~/types/pos'
import { apiFetch } from '~/services/http'

export function fetchDevices(restaurantId: number) {
  return apiFetch<PosDevice[]>(`/api/v1/admin/devices?restaurant_id=${restaurantId}`)
}

export function pairDevice(restaurantId: number, label: string, kind: DeviceKind = 'TILL') {
  return apiFetch<DevicePairResult>(`/api/v1/admin/devices?restaurant_id=${restaurantId}`, {
    method: 'POST',
    body: JSON.stringify({ label, kind }),
  })
}

export function revokeDevice(restaurantId: number, deviceId: number) {
  return apiFetch<void>(`/api/v1/admin/devices/${deviceId}/revoke?restaurant_id=${restaurantId}`, {
    method: 'POST',
  })
}

export function setStaffPin(restaurantId: number, membershipId: number, pin: string) {
  return apiFetch<void>(`/api/v1/admin/devices/staff/${membershipId}/pin?restaurant_id=${restaurantId}`, {
    method: 'POST',
    body: JSON.stringify({ pin }),
  })
}
