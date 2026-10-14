import { apiFetch } from './client';
import type {
  Category,
  MenuListResponse,
  OpenTableSessionsResponse,
  PinLoginResponse,
  PosOrderItem,
  PosOrderRead,
} from './types';

export function pinLogin(deviceToken: string, pin: string) {
  return apiFetch<PinLoginResponse>('/pos/auth/pin-login', { method: 'POST', token: deviceToken, body: { pin } });
}

export function fetchCategories(restaurantId: number) {
  return apiFetch<Category[]>('/categories', { params: { restaurant_id: restaurantId } });
}

export function fetchMenu(restaurantId: number) {
  // page_size large enough that a single restaurant's whole menu fits on one page — fine for this
  // milestone; proper pagination can come later if a menu ever genuinely needs it.
  return apiFetch<MenuListResponse>('/menu', { params: { restaurant_id: restaurantId, page_size: 200 } });
}

export function fetchOpenTableSessions(deviceToken: string) {
  return apiFetch<OpenTableSessionsResponse>('/pos/table-sessions/open', { token: deviceToken });
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
