import type { AnalyticsResponse, DateRangePreset } from '~/types/analytics'
import type { DashboardStats, CustomerSummary, KitchenBoard } from '~/types/admin'
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

export function fetchAdminTables(restaurantId: number) {
  return apiFetch<RestaurantTable[]>(q(restaurantId, '/tables'))
}

export function updateTableStatus(restaurantId: number, tableId: number, status: string) {
  return apiFetch(q(restaurantId, `/tables/${tableId}/status`), {
    method: 'PATCH',
    body: JSON.stringify({ status }),
  })
}

export function fetchAdminCustomers(restaurantId: number) {
  return apiFetch<CustomerSummary[]>(q(restaurantId, '/customers'))
}

export function fetchAdminCustomer(restaurantId: number, userId: number) {
  return apiFetch<{ user_id: number; total_orders: number; total_spending: string; orders: Order[] }>(
    q(restaurantId, `/customers/${userId}`),
  )
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
