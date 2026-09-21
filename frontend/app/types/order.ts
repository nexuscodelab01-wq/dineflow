export type OrderType = 'DINE_IN' | 'PICKUP' | 'DELIVERY'

export type OrderStatus =
  | 'PENDING'
  | 'CONFIRMED'
  | 'PREPARING'
  | 'READY'
  | 'OUT_FOR_DELIVERY'
  | 'DELIVERED'
  | 'COMPLETED'
  | 'CANCELLED'

export type OrderItemModifier = {
  id: number
  modifier_name: string
  option_name: string
  price_adjustment: string
}

export type OrderItem = {
  id: number
  menu_item_id: number
  item_name: string
  quantity: number
  unit_price: string
  line_total: string
  special_instructions?: string | null
  /** KITCHEN, BAR or DESSERT: the screen that makes it. */
  station?: string
  /** NEW until its station bumps it, then READY. */
  status?: 'NEW' | 'READY'
  ready_at?: string | null
  modifiers: OrderItemModifier[]
}

export type OrderStatusHistory = {
  id: number
  previous_status: OrderStatus | null
  new_status: OrderStatus
  created_at: string
}

export type Order = {
  id: number
  order_number: string
  restaurant_id: number
  order_type: OrderType
  /** Table name for dine-in orders. */
  table_number?: string | null
  status: OrderStatus
  subtotal: string
  tax: string
  delivery_fee: string
  discount: string
  total: string
  customer_name: string
  customer_email: string
  customer_phone?: string | null
  delivery_instructions?: string | null
  notes?: string | null
  created_at: string
  updated_at: string
  items: OrderItem[]
  status_history: OrderStatusHistory[]
  payments: { id: number; amount: string; status: string; payment_method: string }[]
}

export type OrderListResponse = {
  items: Order[]
  total: number
  page: number
  page_size: number
  pages: number
}

export type DeliveryAddressInput = {
  street: string
  city: string
  postal_code: string
  delivery_instructions?: string
}

export type OrderItemInput = {
  menu_item_id: number
  quantity: number
  modifier_option_ids: number[]
  special_instructions?: string
}

export type CreateOrderPayload = {
  restaurant_id: number
  order_type: OrderType
  items: OrderItemInput[]
  customer_name: string
  customer_email: string
  customer_phone?: string
  reservation_id?: number
  delivery_address?: DeliveryAddressInput
  delivery_instructions?: string
  notes?: string
}
