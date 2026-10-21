import type { CreateOrderPayload, DeliveryAddressInput, Order, OrderItemInput, OrderListResponse, OrderType } from '~/types/order'
import { apiFetch } from '~/services/http'

export function createOrder(payload: CreateOrderPayload) {
  return apiFetch<Order>('/api/v1/orders', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function fetchOrders(page = 1, pageSize = 20) {
  return apiFetch<OrderListResponse>(`/api/v1/orders?page=${page}&page_size=${pageSize}`)
}

export function fetchOrder(orderId: number) {
  return apiFetch<Order>(`/api/v1/orders/${orderId}`)
}

export type OrderQuote = { subtotal: string, discount: string, tax: string, delivery_fee: string, total: string }

/** Totals (with address-based tax) for the cart on screen — nothing is saved; the order is priced again when placed. */
export function quoteOrder(payload: { restaurant_id: number, order_type: OrderType, items: OrderItemInput[], coupon_code?: string, delivery_address?: DeliveryAddressInput }) {
  return apiFetch<OrderQuote>('/api/v1/orders/quote', { method: 'POST', body: JSON.stringify(payload) })
}
