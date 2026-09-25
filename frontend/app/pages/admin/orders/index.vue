<script setup lang="ts">
import type { Order, OrderStatus } from '~/types/order'
import { fetchAdminOrders } from '~/services/admin'
import { formatCurrency } from '~/utils/format'

definePageMeta({ layout: 'admin', middleware: ['staff'] })

const admin = useAdminStore()
const orders = ref<Order[]>([])
const loading = ref(true)
const error = ref('')
const statusFilter = ref<OrderStatus | ''>('')

async function load() {
  await admin.initialize()
  if (!admin.restaurantId) return
  loading.value = true
  error.value = ''
  try {
    const response = await fetchAdminOrders(admin.restaurantId, {
      status: statusFilter.value || undefined,
    })
    orders.value = response.items
  }
  catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to load orders'
  }
  finally {
    loading.value = false
  }
}

onMounted(load)
watch(statusFilter, load)
</script>

<template>
  <div>
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="font-display text-2xl font-semibold text-brand-900">Orders</h1>
        <p class="text-sm text-ink-muted">Manage and track restaurant orders</p>
      </div>
      <select v-model="statusFilter" class="rounded-lg border border-brand-200 px-3 py-2 text-sm">
        <option value="">All statuses</option>
        <option value="CONFIRMED">Confirmed</option>
        <option value="PREPARING">Preparing</option>
        <option value="READY">Ready</option>
        <option value="COMPLETED">Completed</option>
        <option value="CANCELLED">Cancelled</option>
      </select>
    </div>

    <LoadingState v-if="loading" class="mt-6" :rows="1" />

    <ErrorState v-else-if="error" class="mt-6" :message="error" @retry="load" />

    <EmptyState
      v-else-if="!orders.length"
      class="mt-6"
      title="No orders yet"
      description="Orders matching your filters will appear here."
    />

    <div v-else class="mt-6 overflow-x-auto rounded-2xl border border-brand-100 bg-surface-elevated">
      <table class="min-w-full text-left text-sm">
        <thead class="border-b border-brand-100 bg-brand-50/50 text-xs uppercase tracking-wide text-ink-subtle">
          <tr>
            <th class="px-4 py-3">Order</th>
            <th class="px-4 py-3">Customer</th>
            <th class="px-4 py-3">Type</th>
            <th class="px-4 py-3">Total</th>
            <th class="px-4 py-3">Status</th>
            <th class="px-4 py-3">Created</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="order in orders" :key="order.id" class="border-b border-brand-50 hover:bg-brand-50/40">
            <td class="px-4 py-3">
              <NuxtLink :to="`/admin/orders/${order.id}`" class="font-medium text-brand-700 hover:underline">
                {{ order.order_number }}
              </NuxtLink>
              <span
                v-if="order.scheduled_for"
                class="ml-2 whitespace-nowrap rounded-full bg-brand-100 px-2 py-0.5 text-xs font-semibold text-brand-800"
                :title="`Collection: ${new Date(order.scheduled_for).toLocaleString()}`"
              >
                for {{ new Date(order.scheduled_for).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }) }}
              </span>
            </td>
            <td class="px-4 py-3">{{ order.customer_name }}</td>
            <td class="px-4 py-3">{{ order.order_type.replace('_', ' ') }}</td>
            <td class="px-4 py-3">{{ formatCurrency(Number(order.total)) }}</td>
            <td class="px-4 py-3"><StatusBadge :status="order.status" /></td>
            <td class="px-4 py-3 text-ink-muted">{{ new Date(order.created_at).toLocaleString() }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
