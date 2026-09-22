import type { Restaurant } from '~/types/menu'
import type { TenantCreatePayload, TenantCreateResponse } from '~/types/platform'
import { apiFetch } from '~/services/http'

export function fetchAllRestaurants() {
  return apiFetch<Restaurant[]>('/api/v1/restaurants')
}

export function fetchTenantTemplates() {
  return apiFetch<string[]>('/api/v1/platform/restaurants/templates')
}

export function createTenant(payload: TenantCreatePayload) {
  const form = new FormData()
  form.set('name', payload.name)
  form.set('slug', payload.slug)
  form.set('owner_email', payload.owner_email)
  if (payload.owner_name) form.set('owner_name', payload.owner_name)
  if (payload.color) form.set('color', payload.color)
  if (payload.secondary_color) form.set('secondary_color', payload.secondary_color)
  if (payload.template) form.set('template', payload.template)
  if (payload.timezone) form.set('timezone', payload.timezone)
  if (payload.custom_domain) form.set('custom_domain', payload.custom_domain)
  form.set('branding', String(payload.branding ?? true))
  form.set('send_invite', String(payload.send_invite ?? false))
  if (payload.logo) form.set('logo', payload.logo)
  return apiFetch<TenantCreateResponse>('/api/v1/platform/restaurants', { method: 'POST', body: form })
}

export function verifyRestaurantDomain(restaurantId: number) {
  return apiFetch<Restaurant>(`/api/v1/platform/restaurants/${restaurantId}/verify-domain`, { method: 'POST' })
}
