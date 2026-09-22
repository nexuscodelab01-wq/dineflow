export type DashboardStats = {
  today_orders: number
  today_revenue: string
  pending_orders: number
  completed_orders_today: number
  average_order_value: string
}

export type CustomerSummary = {
  id: number
  email: string
  first_name: string
  last_name: string
  phone?: string | null
  is_active: boolean
  is_vip: boolean
  notes?: string | null
  allergies?: string | null
  total_orders: number
  total_spending: string
  last_order_at?: string | null
  total_bookings: number
  /** The more recent of their last order and last booking. */
  last_seen_at?: string | null
}

export type CustomerReservationBrief = {
  id: number
  starts_at: string
  party_size: number
  status: string
  table_number?: string | null
}

export type CustomerDetail = {
  id: number
  email: string
  first_name: string
  last_name: string
  phone?: string | null
  is_active: boolean
  is_vip: boolean
  notes?: string | null
  allergies?: string | null
  total_orders: number
  total_spending: string
  total_bookings: number
  orders: import('~/types/order').Order[]
  reservations: CustomerReservationBrief[]
}

export type CustomerProfileUpdate = {
  notes?: string | null
  allergies?: string | null
  is_vip?: boolean
}

export type KitchenBoard = {
  new_orders: import('~/types/order').Order[]
  preparing: import('~/types/order').Order[]
  ready: import('~/types/order').Order[]
}
