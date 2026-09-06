import type { DashboardStats } from '~/types/admin'

export type DateRangePreset =
  | 'today'
  | 'yesterday'
  | 'last_7_days'
  | 'last_30_days'
  | 'this_month'
  | 'last_month'
  | 'custom'

export type TimeSeriesPoint = {
  date: string
  orders: number
  revenue: string
}

export type CategoryBreakdown = {
  category_name: string
  order_count: number
  revenue: string
}

export type PopularItem = {
  item_name: string
  quantity: number
  revenue: string
}

export type StatusBreakdown = {
  status: string
  count: number
}

export type AnalyticsResponse = {
  preset: string
  start_date: string
  end_date: string
  summary: DashboardStats
  revenue_over_time: TimeSeriesPoint[]
  orders_over_time: TimeSeriesPoint[]
  orders_by_category: CategoryBreakdown[]
  popular_items: PopularItem[]
  order_status_distribution: StatusBreakdown[]
}

export const DATE_RANGE_OPTIONS: { value: DateRangePreset; label: string }[] = [
  { value: 'today', label: 'Today' },
  { value: 'yesterday', label: 'Yesterday' },
  { value: 'last_7_days', label: 'Last 7 days' },
  { value: 'last_30_days', label: 'Last 30 days' },
  { value: 'this_month', label: 'This month' },
  { value: 'last_month', label: 'Last month' },
  { value: 'custom', label: 'Custom range' },
]
