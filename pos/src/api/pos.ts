import { apiFetch } from './client';
import type {
  CashMovementKind,
  Category,
  MenuListResponse,
  OpenSession,
  OpenTableSessionsResponse,
  PinLoginResponse,
  PosCardIntentRead,
  PosConnectionTokenResponse,
  PosOrderItem,
  PosOrderRead,
  RestaurantTableRow,
  ShiftReportRead,
  ShiftRead,
  TablePaymentRead,
  TimeEntryRead,
} from './types';

export function pinLogin(deviceToken: string, pin: string) {
  return apiFetch<PinLoginResponse>('/pos/auth/pin-login', { method: 'POST', token: deviceToken, body: { pin } });
}

export function fetchCategories(restaurantId: number) {
  return apiFetch<Category[]>('/categories', { params: { restaurant_id: restaurantId } });
}

export function fetchMenu(restaurantId: number) {
  // 100 is the backend's own hard cap (Query(..., le=100) in admin_management.py) — large enough
  // that a single restaurant's whole menu fits on one page for this milestone; proper pagination can
  // come later if a menu ever genuinely needs more than that.
  return apiFetch<MenuListResponse>('/menu', { params: { restaurant_id: restaurantId, page_size: 100 } });
}

export function fetchOpenTableSessions(deviceToken: string) {
  return apiFetch<OpenTableSessionsResponse>('/pos/table-sessions/open', { token: deviceToken });
}

export function fetchTables(deviceToken: string) {
  return apiFetch<RestaurantTableRow[]>('/pos/tables', { token: deviceToken });
}

export function seatTable(posSessionToken: string, tableId: number, partySize?: number) {
  return apiFetch<OpenSession>(`/pos/tables/${tableId}/seat`, {
    method: 'POST', token: posSessionToken, body: { party_size: partySize ?? null },
  });
}

export function createCounterOrder(posSessionToken: string, items: PosOrderItem[], notes?: string) {
  return apiFetch<PosOrderRead>('/pos/orders', { method: 'POST', token: posSessionToken, body: { items, notes } });
}

export function createTableOrder(posSessionToken: string, sessionId: number, items: PosOrderItem[], notes?: string) {
  return apiFetch('/pos/table-sessions/' + sessionId + '/orders', {
    method: 'POST', token: posSessionToken, body: { items, notes },
  });
}

export function payCash(posSessionToken: string, orderId: number) {
  return apiFetch<void>(`/pos/orders/${orderId}/pay-cash`, { method: 'POST', token: posSessionToken });
}

export function createCardIntent(posSessionToken: string, orderId: number) {
  return apiFetch<PosCardIntentRead>(`/pos/orders/${orderId}/pay-card`, { method: 'POST', token: posSessionToken });
}

export function createTableCardIntent(posSessionToken: string, sessionId: number) {
  return apiFetch<TablePaymentRead>(`/pos/table-sessions/${sessionId}/pay-card`, { method: 'POST', token: posSessionToken });
}

export function payCashForTable(posSessionToken: string, sessionId: number) {
  return apiFetch<void>(`/pos/table-sessions/${sessionId}/pay-cash`, { method: 'POST', token: posSessionToken });
}

export function fetchTerminalConnectionToken(posSessionToken: string) {
  return apiFetch<PosConnectionTokenResponse>('/pos/terminal/connection-token', { method: 'POST', token: posSessionToken });
}

export function fetchCurrentShift(deviceToken: string) {
  return apiFetch<ShiftRead | null>('/pos/shifts/current', { token: deviceToken });
}

export function openShift(posSessionToken: string, startingFloat: string) {
  return apiFetch<ShiftRead>('/pos/shifts/open', { method: 'POST', token: posSessionToken, body: { starting_float: startingFloat } });
}

export function closeShift(posSessionToken: string, shiftId: number, countedCash: string) {
  return apiFetch<ShiftReportRead>(`/pos/shifts/${shiftId}/close`, { method: 'POST', token: posSessionToken, body: { counted_cash: countedCash } });
}

export function recordCashMovement(posSessionToken: string, shiftId: number, kind: CashMovementKind, amount: string, reason: string) {
  return apiFetch<void>(`/pos/shifts/${shiftId}/cash-movement`, { method: 'POST', token: posSessionToken, body: { kind, amount, reason } });
}

export function fetchCurrentTimeEntry(posSessionToken: string) {
  return apiFetch<TimeEntryRead | null>('/pos/time-entries/current', { token: posSessionToken });
}

export function clockIn(posSessionToken: string) {
  return apiFetch<TimeEntryRead>('/pos/time-entries/clock-in', { method: 'POST', token: posSessionToken });
}

export function clockOut(posSessionToken: string) {
  return apiFetch<TimeEntryRead>('/pos/time-entries/clock-out', { method: 'POST', token: posSessionToken });
}
