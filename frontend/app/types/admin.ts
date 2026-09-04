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
  total_orders: number
  total_spending: string
  last_order_at?: string | null
}

export type KitchenBoard = {
  new_orders: import('~/types/order').Order[]
  preparing: import('~/types/order').Order[]
  ready: import('~/types/order').Order[]
}
