<script setup lang="ts">
import type { Order } from '~/types/order'
import { fetchOrders } from '~/services/orders'
import { formatCurrency } from '~/utils/format'

definePageMeta({ middleware: ['auth'] })

const orders = ref<Order[]>([])
const loading = ref(true)
const error = ref('')

onMounted(async () => {
  try {
    const response = await fetchOrders()
    orders.value = response.items
  }
  catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to load orders'
  }
  finally {
    loading.value = false
  }
})

function statusClass(status: string) {
  if (status === 'CANCELLED') return 'bg-red-100 text-red-800'
  if (status === 'COMPLETED' || status === 'DELIVERED') return 'bg-green-100 text-green-800'
  return 'bg-brand-100 text-brand-800'
}
</script>

<template>
  <div class="mx-auto max-w-3xl px-4 py-8 sm:px-6">
    <h1 class="font-display text-3xl font-semibold text-brand-900">Your orders</h1>

    <div v-if="loading" class="mt-8 space-y-3">
      <div v-for="n in 3" :key="n" class="h-24 animate-pulse rounded-2xl bg-brand-100/60" />
    </div>

    <p v-else-if="error" class="mt-6 text-sm text-red-600">{{ error }}</p>

    <div v-else-if="!orders.length" class="mt-10 rounded-2xl border border-dashed border-brand-200 py-16 text-center text-ink-muted">
      No orders yet. <NuxtLink to="/menu" class="font-semibold text-brand-700">Order now</NuxtLink>
    </div>

    <div v-else class="mt-6 space-y-4">
      <NuxtLink
        v-for="order in orders"
        :key="order.id"
        :to="`/orders/${order.id}`"
        class="block rounded-2xl border border-brand-100 bg-surface-elevated p-4 transition hover:border-brand-300 hover:shadow-sm"
      >
        <div class="flex items-start justify-between gap-4">
          <div>
            <p class="font-semibold text-ink">{{ order.order_number }}</p>
            <p class="mt-1 text-sm text-ink-muted">{{ new Date(order.created_at).toLocaleString() }}</p>
            <p class="mt-1 text-sm text-ink-muted">{{ order.items.length }} item(s) · {{ order.order_type.replace('_', ' ') }}</p>
          </div>
          <div class="text-right">
            <span class="rounded-full px-2.5 py-1 text-xs font-medium" :class="statusClass(order.status)">{{ order.status.replace('_', ' ') }}</span>
            <p class="mt-2 font-semibold text-brand-800">{{ formatCurrency(Number(order.total)) }}</p>
          </div>
        </div>
      </NuxtLink>
    </div>
  </div>
</template>
