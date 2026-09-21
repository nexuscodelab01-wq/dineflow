import type { Category, MenuFilters, MenuItemDetail, MenuListResponse, Restaurant, RestaurantTable } from '~/types/menu'
import { apiFetch } from '~/services/http'

/** The restaurant whose site is at this address (host, e.g. "pizza.dineflow.app"). */
export function fetchTenant(host: string) {
  return apiFetch<Restaurant>(`/api/v1/tenant?host=${encodeURIComponent(host)}`, { auth: false })
}

/** Restaurants the signed-in account can manage (memberships; every restaurant for platform admins). */
export function fetchMyRestaurants() {
  return apiFetch<Restaurant[]>('/api/v1/auth/my-restaurants')
}

export function fetchRestaurant(identifier: string) {
  return apiFetch<Restaurant>(`/api/v1/restaurants/${identifier}`, { auth: false })
}

export function fetchCategories(restaurantId: number) {
  return apiFetch<Category[]>(`/api/v1/categories?restaurant_id=${restaurantId}`, { auth: false })
}

export function fetchMenu(restaurantId: number, filters: MenuFilters = {}) {
  const params = new URLSearchParams({ restaurant_id: String(restaurantId) })
  if (filters.search) params.set('search', filters.search)
  if (filters.category_id) params.set('category_id', String(filters.category_id))
  if (filters.is_vegetarian) params.set('is_vegetarian', 'true')
  if (filters.is_spicy) params.set('is_spicy', 'true')
  if (filters.is_popular) params.set('is_popular', 'true')
  if (filters.price_min != null) params.set('price_min', String(filters.price_min))
  if (filters.price_max != null) params.set('price_max', String(filters.price_max))
  if (filters.sort) params.set('sort', filters.sort)
  if (filters.page) params.set('page', String(filters.page))
  if (filters.page_size) params.set('page_size', String(filters.page_size))
  return apiFetch<MenuListResponse>(`/api/v1/menu?${params}`, { auth: false })
}

export function fetchMenuItem(itemId: number, restaurantId: number) {
  return apiFetch<MenuItemDetail>(`/api/v1/menu/${itemId}?restaurant_id=${restaurantId}`, { auth: false })
}

export function fetchRestaurantTables(identifier: string, availableOnly = true) {
  const params = availableOnly ? '?available_only=true' : '?available_only=false'
  return apiFetch<RestaurantTable[]>(`/api/v1/restaurants/${identifier}/tables${params}`, { auth: false })
}
