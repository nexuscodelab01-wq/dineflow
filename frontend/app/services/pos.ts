import type { CardReader, DeviceKind, DevicePairResult, DevicePrinter, PosDevice } from '~/types/pos'
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

/** The device's receipt printer: a network address (ESC/POS, usually port 9100), cash-drawer kick, auto-print. */
export function updateDevicePrinter(restaurantId: number, deviceId: number, printer: { printer_host: string | null, printer_port: number, cash_drawer: boolean, auto_print: boolean }) {
  return apiFetch<PosDevice & { printer: DevicePrinter }>(`/api/v1/admin/devices/${deviceId}?restaurant_id=${restaurantId}`, {
    method: 'PATCH',
    body: JSON.stringify(printer),
  })
}

export function fetchReaders(restaurantId: number) {
  return apiFetch<CardReader[]>(`/api/v1/admin/terminal/readers?restaurant_id=${restaurantId}`)
}

export function registerReader(restaurantId: number, registrationCode: string, label: string) {
  return apiFetch<CardReader>(`/api/v1/admin/terminal/readers?restaurant_id=${restaurantId}`, {
    method: 'POST',
    body: JSON.stringify({ registration_code: registrationCode, label }),
  })
}

/** Test mode only: act as if a customer tapped a test card on a simulated reader. */
export function simulateReaderTap(restaurantId: number, readerId: string) {
  return apiFetch<void>(`/api/v1/admin/terminal/readers/${readerId}/simulate-tap?restaurant_id=${restaurantId}`, { method: 'POST' })
}

export function removeReader(restaurantId: number, readerId: string) {
  return apiFetch<void>(`/api/v1/admin/terminal/readers/${readerId}?restaurant_id=${restaurantId}`, { method: 'DELETE' })
}
