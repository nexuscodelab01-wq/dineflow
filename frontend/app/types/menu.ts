export type Restaurant = {
  id: number
  name: string
  slug: string
  description?: string | null
  logo_url?: string | null
  address?: string | null
  city?: string | null
  postal_code?: string | null
  phone?: string | null
  email?: string | null
  delivery_enabled: boolean
  pickup_enabled: boolean
  dine_in_enabled: boolean
  tax_rate: string
  delivery_fee: string
  is_active: boolean
}

export type Category = {
  id: number
  name: string
  slug: string
  description?: string | null
  sort_order: number
  is_active: boolean
}

export type ModifierOption = {
  id: number
  name: string
  price_adjustment: string
  is_default: boolean
  sort_order: number
}

export type MenuModifier = {
  id: number
  name: string
  description?: string | null
  is_required: boolean
  min_selections: number
  max_selections: number
  sort_order: number
  options: ModifierOption[]
}

export type MenuItem = {
  id: number
  restaurant_id: number
  category_id: number
  category_name?: string | null
  name: string
  description?: string | null
  price: string
  image_url?: string | null
  is_available: boolean
  preparation_time_minutes: number
  is_vegetarian: boolean
  is_spicy: boolean
  is_popular: boolean
}

export type MenuItemDetail = MenuItem & {
  modifiers: MenuModifier[]
}

export type MenuListResponse = {
  items: MenuItem[]
  total: number
  page: number
  page_size: number
  pages: number
}

export type MenuFilters = {
  search?: string
  category_id?: number
  is_vegetarian?: boolean
  is_spicy?: boolean
  is_popular?: boolean
  price_min?: number
  price_max?: number
  sort?: 'popular' | 'name' | 'price_asc' | 'price_desc'
  page?: number
  page_size?: number
}

export type RestaurantTable = {
  id: number
  table_number: string
  capacity: number
  status: string
}
