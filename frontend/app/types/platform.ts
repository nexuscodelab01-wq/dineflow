export type TenantCreatePayload = {
  name: string
  slug: string
  owner_email: string
  owner_name?: string
  color?: string
  secondary_color?: string
  template?: string
  timezone?: string
  custom_domain?: string
  branding?: boolean
  send_invite?: boolean
  logo?: File | null
}

export type TenantCreateResponse = {
  restaurant_id: number
  name: string
  slug: string
  order_prefix: string
  owner_email: string
  site_url: string
  invite_link?: string | null
}

/** One flag in the global catalog — no restaurant in view, so no override/enabled here. */
export type FeatureCatalogEntry = {
  key: string
  description: string
  default: boolean
}

export type FeatureCreatePayload = {
  key: string
  description: string
  default: boolean
}

/** One flag's effective value for a specific restaurant (GET .../restaurants/{id}/features). */
export type RestaurantFeature = {
  key: string
  description: string
  default: boolean
  override: boolean | null
  enabled: boolean
}
