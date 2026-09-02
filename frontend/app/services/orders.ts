import type { CreateOrderPayload, Order, OrderListResponse } from '~/types/order'
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
