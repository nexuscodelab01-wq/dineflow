import type { JoinResponse, OpenTableSession, QrTable, ServiceRequest, SessionRound, TableInfo, TableSessionView, WaiterTable } from '~/types/table'
import { apiFetch } from '~/services/http'

const json = (body: unknown) => JSON.stringify(body)
const pass = (token: string) => ({ Authorization: `Bearer ${token}` })

// ---- guests: no account, only the table's QR code and the pass it hands out ----------------------

export function fetchTableInfo(tableToken: string, restaurantId: number) {
  return apiFetch<TableInfo>(`/api/v1/t/${encodeURIComponent(tableToken)}?restaurant_id=${restaurantId}`, { auth: false })
}

export function joinTable(tableToken: string, restaurantId: number, name: string | null) {
  return apiFetch<JoinResponse>(`/api/v1/t/${encodeURIComponent(tableToken)}/join?restaurant_id=${restaurantId}`, {
    method: 'POST', body: json({ name }), auth: false,
  })
}

export function fetchTableSession(token: string) {
  return apiFetch<TableSessionView>('/api/v1/table-session', { auth: false, headers: pass(token) })
}

/** `key` makes the send retry-safe: the same key always yields the same round, however often it is tapped. */
export function sendRound(token: string, payload: unknown, key: string) {
  return apiFetch<SessionRound>('/api/v1/table-session/orders', {
    method: 'POST', body: json(payload), auth: false, headers: { ...pass(token), 'Idempotency-Key': key },
  })
}

// ---- staff ---------------------------------------------------------------------------------------

export function fetchQrTables(restaurantId: number) {
  return apiFetch<QrTable[]>(`/api/v1/admin/qr/tables?restaurant_id=${restaurantId}`)
}

export function rotateQr(restaurantId: number, tableId: number) {
  return apiFetch<QrTable>(`/api/v1/admin/tables/${tableId}/qr/rotate?restaurant_id=${restaurantId}`, { method: 'POST' })
}

export function fetchOpenSessions(restaurantId: number) {
  return apiFetch<OpenTableSession[]>(`/api/v1/admin/table-sessions?restaurant_id=${restaurantId}`)
}

export function closeSession(restaurantId: number, sessionId: number) {
  return apiFetch<void>(`/api/v1/admin/table-sessions/${sessionId}/close?restaurant_id=${restaurantId}`, { method: 'POST' })
}

export function askForService(token: string, kind: 'WAITER' | 'BILL') {
  return apiFetch<string[]>('/api/v1/table-session/requests', { method: 'POST', body: json({ kind }), auth: false, headers: pass(token) })
}

export function fetchServiceRequests(restaurantId: number) {
  return apiFetch<ServiceRequest[]>(`/api/v1/admin/service-requests?restaurant_id=${restaurantId}`)
}

export function finishServiceRequest(restaurantId: number, requestId: number) {
  return apiFetch<void>(`/api/v1/admin/service-requests/${requestId}/done?restaurant_id=${restaurantId}`, { method: 'POST' })
}

// ---- waiter view ---------------------------------------------------------------------------------

export function fetchWaiterFloor(restaurantId: number) {
  return apiFetch<WaiterTable[]>(`/api/v1/admin/waiter/floor?restaurant_id=${restaurantId}`)
}

export function fetchTabDetail(restaurantId: number, sessionId: number) {
  return apiFetch<TableSessionView>(`/api/v1/admin/table-sessions/${sessionId}?restaurant_id=${restaurantId}`)
}

/** A waiter sends a round on the table's behalf. */
export function sendStaffRound(restaurantId: number, sessionId: number, payload: unknown, key: string) {
  return apiFetch<SessionRound>(`/api/v1/admin/table-sessions/${sessionId}/orders?restaurant_id=${restaurantId}`, {
    method: 'POST', body: json(payload), headers: { 'Idempotency-Key': key },
  })
}

export function transferTab(restaurantId: number, sessionId: number, tableId: number) {
  return apiFetch<void>(`/api/v1/admin/table-sessions/${sessionId}/transfer?restaurant_id=${restaurantId}`, {
    method: 'POST', body: json({ table_id: tableId }),
  })
}
