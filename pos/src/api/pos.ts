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
  AdjustmentResult,
  AwaitingPayment,
  SplitPayload,
  CouponPreview,
  MenuItemDetail,
  MenuListResponse as PosMenuResponse,
  PosCustomer,
  ControlAction,
  ControlKind,
  Reasons,
  RecentPayment,
  TabDetail,
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

export function seatTable(posSessionToken: string, tableId: number, partySize?: number, tabName?: string) {
  return apiFetch<OpenSession>(`/pos/tables/${tableId}/seat`, {
    method: 'POST', token: posSessionToken, body: { party_size: partySize ?? null, tab_name: tabName || null },
  });
}

export function createCounterOrder(
  posSessionToken: string, items: PosOrderItem[], notes?: string, extras?: { customerId?: number; couponCode?: string },
) {
  return apiFetch<PosOrderRead>('/pos/orders', {
    method: 'POST', token: posSessionToken,
    body: { items, notes, customer_id: extras?.customerId, coupon_code: extras?.couponCode },
  });
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

export function createTableCardIntent(posSessionToken: string, sessionId: number, split?: SplitPayload) {
  return apiFetch<TablePaymentRead>(`/pos/table-sessions/${sessionId}/pay-card`, { method: 'POST', token: posSessionToken, body: split });
}

export function payCashForTable(posSessionToken: string, sessionId: number, split?: SplitPayload) {
  return apiFetch<void>(`/pos/table-sessions/${sessionId}/pay-cash`, { method: 'POST', token: posSessionToken, body: split });
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

export function closeShift(posSessionToken: string, shiftId: number, countedCash: string, cashTips = '0') {
  return apiFetch<ShiftReportRead>(`/pos/shifts/${shiftId}/close`, { method: 'POST', token: posSessionToken, body: { counted_cash: countedCash, cash_tips: cashTips } });
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

/** A handheld server also sends their cash-up (cash on hand + the cash tips among it). */
export function clockOut(posSessionToken: string, cashUp?: { countedCash: string; cashTips: string }) {
  return apiFetch<TimeEntryRead>('/pos/time-entries/clock-out', {
    method: 'POST', token: posSessionToken,
    body: cashUp ? { counted_cash: cashUp.countedCash, cash_tips: cashUp.cashTips } : undefined,
  });
}

// ---- POS controls: voids, comps, discounts, refunds, manager approval --------------------------------

type ControlFields = { reason_code: string; note?: string };

export function fetchReasons(token: string) {
  return apiFetch<Reasons>('/pos/reasons', { token });
}

/** A manager types their own PIN to approve one action; returns a short-lived token to send with it. */
export function authorizeAction(token: string, pin: string, action: ControlAction) {
  return apiFetch<{ token: string; approver: string; expires_in: number }>('/pos/authorize', { method: 'POST', token, body: { pin, action } });
}

export function fetchTab(token: string, sessionId: number) {
  return apiFetch<TabDetail>(`/pos/table-sessions/${sessionId}`, { token });
}

export function fetchRecentPayments(token: string) {
  return apiFetch<RecentPayment[]>('/pos/recent-payments', { token });
}

/** One entry point for every controlled action, so the approval retry is the same everywhere. */
export function runControl(
  token: string,
  kind: ControlKind,
  target: { type: 'item' | 'order' | 'tab'; id: number },
  fields: ControlFields & { percent?: string; quantity?: number },
  override?: string,
) {
  const verb = kind.toLowerCase();
  const path =
    kind === 'REFUND'
      ? target.type === 'tab' ? `/pos/table-sessions/${target.id}/refund` : `/pos/orders/${target.id}/refund`
      : target.type === 'item' ? `/pos/order-items/${target.id}/${verb}`
      : target.type === 'order' ? `/pos/orders/${target.id}/discount`
      : `/pos/table-sessions/${target.id}/discount`;
  return apiFetch<AdjustmentResult>(path, { method: 'POST', token, body: fields, headers: override ? { 'X-Manager-Override': override } : undefined });
}

// ---- everyday till features ------------------------------------------------------------------------

/** The whole menu for the till, sold-out dishes included so they can be brought back. */
export function fetchPosMenu(token: string) {
  return apiFetch<PosMenuResponse>('/pos/menu', { token });
}

export function fetchItemDetail(restaurantId: number, itemId: number) {
  return apiFetch<MenuItemDetail>(`/menu/${itemId}`, { params: { restaurant_id: restaurantId } });
}

export function setItemAvailability(token: string, itemId: number, isAvailable: boolean) {
  return apiFetch<{ item_id: number; is_available: boolean }>(`/pos/menu-items/${itemId}/availability`, {
    method: 'POST', token, body: { is_available: isAvailable },
  });
}

export function searchCustomers(token: string, q: string) {
  return apiFetch<PosCustomer[]>('/pos/customers', { token, params: { q } });
}

export function previewCoupon(token: string, code: string, subtotal: number, customerId?: number) {
  return apiFetch<CouponPreview>('/pos/coupons/preview', {
    method: 'POST', token, body: { code, subtotal: subtotal.toFixed(2), customer_id: customerId },
  });
}

/** X-report: where the till stands now; closes nothing. */
export function fetchXReport(token: string) {
  return apiFetch<ShiftReportRead>('/pos/shifts/current/report', { token });
}

/** Online pay-at-pickup / cash-on-delivery orders that still owe money. */
export function fetchAwaitingPayment(token: string) {
  return apiFetch<AwaitingPayment[]>('/pos/orders/awaiting-payment', { token });
}

// ---- floor ops: move, merge, fire a course ---------------------------------------------------------

export function moveTab(token: string, sessionId: number, tableId: number) {
  return apiFetch<void>(`/pos/table-sessions/${sessionId}/move`, { method: 'POST', token, body: { table_id: tableId } });
}

export function mergeTab(token: string, sessionId: number, intoSessionId: number) {
  return apiFetch<void>(`/pos/table-sessions/${sessionId}/merge`, { method: 'POST', token, body: { into_session_id: intoSessionId } });
}

export function fireCourse(token: string, sessionId: number, course: number) {
  return apiFetch<{ fired: number }>(`/pos/table-sessions/${sessionId}/fire`, { method: 'POST', token, body: { course } });
}
