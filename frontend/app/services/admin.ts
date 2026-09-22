import type { AnalyticsResponse, DateRangePreset } from '~/types/analytics'
import type { CustomerDetail, CustomerProfileUpdate, CustomerSummary, DashboardStats, KitchenBoard } from '~/types/admin'
import type { Category, MenuItemDetail, MenuModifier, Restaurant, RestaurantTable } from '~/types/menu'
import type { Order, OrderListResponse, OrderStatus } from '~/types/order'
import { apiFetch } from '~/services/http'

function q(restaurantId: number, extra = '') {
  return `/api/v1/admin${extra}${extra.includes('?') ? '&' : '?'}restaurant_id=${restaurantId}`
}

export function fetchDashboard(restaurantId: number) {
  return apiFetch<DashboardStats>(q(restaurantId, '/dashboard'))
}

export function fetchAnalytics(
  restaurantId: number,
  range: DateRangePreset = 'last_7_days',
  startDate?: string,
  endDate?: string,
) {
  const params = new URLSearchParams({
    restaurant_id: String(restaurantId),
    range,
  })
  if (range === 'custom' && startDate && endDate) {
    params.set('start_date', startDate)
    params.set('end_date', endDate)
  }
  return apiFetch<AnalyticsResponse>(`/api/v1/admin/analytics?${params}`)
}

export function fetchAdminCategories(restaurantId: number) {
  return apiFetch<Category[]>(q(restaurantId, '/categories'))
}

export function fetchAdminMenu(restaurantId: number) {
  return apiFetch<MenuItemDetail[]>(q(restaurantId, '/menu'))
}

export function fetchAdminModifiers(restaurantId: number) {
  return apiFetch<MenuModifier[]>(q(restaurantId, '/modifiers'))
}

export function fetchAdminOrders(restaurantId: number, params: Record<string, string | number | undefined> = {}) {
  const search = new URLSearchParams({ restaurant_id: String(restaurantId) })
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== '') search.set(key, String(value))
  }
  return apiFetch<OrderListResponse>(`/api/v1/admin/orders?${search}`)
}

export function fetchAdminOrder(restaurantId: number, orderId: number) {
  return apiFetch<Order>(q(restaurantId, `/orders/${orderId}`))
}

export function updateOrderStatus(restaurantId: number, orderId: number, status: OrderStatus, notes?: string) {
  return apiFetch<Order>(q(restaurantId, `/orders/${orderId}/status`), {
    method: 'PATCH',
    body: JSON.stringify({ status, notes }),
  })
}

export function fetchKitchenBoard(restaurantId: number) {
  return apiFetch<KitchenBoard>(q(restaurantId, '/kitchen'))
}

export function fetchAdminTables(restaurantId: number, includeInactive = false) {
  return apiFetch<RestaurantTable[]>(q(restaurantId, `/tables${includeInactive ? '?include_inactive=true' : ''}`))
}

export type TablePayload = {
  table_number: string
  capacity: number
  zone?: string | null
  shape?: 'ROUND' | 'SQUARE' | 'RECT'
  pos_x?: number | null
  pos_y?: number | null
}

export function createTable(restaurantId: number, payload: TablePayload) {
  return apiFetch<RestaurantTable>(q(restaurantId, '/tables'), {
    method: 'POST',
    body: JSON.stringify({ ...payload, restaurant_id: restaurantId }),
  })
}

/** Only the fields you pass change; send `zone: null` to clear the zone. */
export function updateTable(restaurantId: number, tableId: number, payload: Partial<TablePayload> & { is_active?: boolean }) {
  return apiFetch<RestaurantTable>(q(restaurantId, `/tables/${tableId}`), {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export function deleteTable(restaurantId: number, tableId: number) {
  return apiFetch<void>(q(restaurantId, `/tables/${tableId}`), { method: 'DELETE' })
}

/** Save floor-plan positions for several tables at once. */
export function saveTableLayout(restaurantId: number, items: { id: number, pos_x: number, pos_y: number }[]) {
  return apiFetch<RestaurantTable[]>(q(restaurantId, '/tables/layout'), {
    method: 'PUT',
    body: JSON.stringify({ items }),
  })
}

export type TableStatusResult = {
  id: number
  status: string
  cancelled_reservations: number
  completed_reservations: number
}

/** `force` confirms releasing/cleaning a table that still has an active or imminent booking. */
export function updateTableStatus(restaurantId: number, tableId: number, status: string, force = false) {
  return apiFetch<TableStatusResult>(q(restaurantId, `/tables/${tableId}/status`), {
    method: 'PATCH',
    body: JSON.stringify({ status, force }),
  })
}

export function fetchAdminCustomers(restaurantId: number) {
  return apiFetch<CustomerSummary[]>(q(restaurantId, '/customers'))
}

export function fetchAdminCustomer(restaurantId: number, userId: number) {
  return apiFetch<CustomerDetail>(q(restaurantId, `/customers/${userId}`))
}

/** Notes, allergies and the VIP flag a restaurant keeps on its own guest. */
export function updateAdminCustomer(restaurantId: number, userId: number, data: CustomerProfileUpdate) {
  return apiFetch<CustomerSummary>(q(restaurantId, `/customers/${userId}`), {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export function fetchAdminSettings(restaurantId: number) {
  return apiFetch<Restaurant>(q(restaurantId, '/settings'))
}

export function updateAdminSettings(restaurantId: number, payload: Partial<Restaurant>) {
  return apiFetch<Restaurant>(q(restaurantId, '/settings'), {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export function createMenuItem(restaurantId: number, payload: Record<string, unknown>) {
  return apiFetch<MenuItemDetail>(q(restaurantId, '/menu'), {
    method: 'POST',
    body: JSON.stringify({ ...payload, restaurant_id: restaurantId }),
  })
}

export function updateMenuItem(restaurantId: number, itemId: number, payload: Record<string, unknown>) {
  return apiFetch<MenuItemDetail>(q(restaurantId, `/menu/${itemId}`), {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export function deleteMenuItem(restaurantId: number, itemId: number) {
  return apiFetch<void>(q(restaurantId, `/menu/${itemId}`), { method: 'DELETE' })
}

export function createCategory(restaurantId: number, payload: Record<string, unknown>) {
  return apiFetch<Category>(q(restaurantId, '/categories'), {
    method: 'POST',
    body: JSON.stringify({ ...payload, restaurant_id: restaurantId }),
  })
}

export function deleteCategory(restaurantId: number, categoryId: number) {
  return apiFetch<void>(q(restaurantId, `/categories/${categoryId}`), { method: 'DELETE' })
}

export function uploadMenuImage(restaurantId: number, file: File) {
  const body = new FormData()
  body.append('file', file)
  return apiFetch<{ url: string, thumb_url?: string | null }>(q(restaurantId, '/uploads/menu-image'), {
    method: 'POST',
    body,
  })
}

/** Restaurant logo (transparency kept). The returned url is saved on the restaurant by the caller. */
export function uploadLogo(restaurantId: number, file: File) {
  const body = new FormData()
  body.append('file', file)
  return apiFetch<{ url: string }>(q(restaurantId, '/uploads/logo'), {
    method: 'POST',
    body,
  })
}

// ---- kitchen screen actions -----------------------------------------------------------------------

export function bumpItem(restaurantId: number, itemId: number) {
  return apiFetch<void>(q(restaurantId, `/kitchen/items/${itemId}/bump`), { method: 'POST' })
}

export function recallItem(restaurantId: number, itemId: number) {
  return apiFetch<void>(q(restaurantId, `/kitchen/items/${itemId}/recall`), { method: 'POST' })
}

/** Bump every open dish on a ticket, or only one station's dishes. */
export function bumpTicket(restaurantId: number, orderId: number, station?: string | null) {
  const path = `/kitchen/orders/${orderId}/bump${station ? `?station=${encodeURIComponent(station)}` : ''}`
  return apiFetch<void>(q(restaurantId, path), { method: 'POST' })
}

/** "86" a dish (or bring it back): unavailable on every menu and for QR ordering at once. */
export function setSoldOut(restaurantId: number, menuItemId: number, soldOut: boolean) {
  return apiFetch<{ id: number, is_available: boolean }>(q(restaurantId, `/menu/${menuItemId}/sold-out`), {
    method: 'POST',
    body: JSON.stringify({ sold_out: soldOut }),
  })
}
