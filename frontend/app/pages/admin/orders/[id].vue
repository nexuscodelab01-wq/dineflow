<script setup lang="ts">
import type { Order, OrderStatus } from '~/types/order'
import { fetchAdminOrder, updateOrderStatus } from '~/services/admin'
import { formatCurrency } from '~/utils/format'

definePageMeta({ layout: 'admin', middleware: ['staff'] })

const route = useRoute()
const admin = useAdminStore()
const order = ref<Order | null>(null)
const loading = ref(true)
const error = ref('')

const orderId = computed(() => Number(route.params.id))

async function load() {
  await admin.initialize()
  if (!admin.restaurantId) return
  loading.value = true
  try {
    order.value = await fetchAdminOrder(admin.restaurantId, orderId.value)
  }
  catch (err) {
    error.value = err instanceof Error ? err.message : 'Order not found'
  }
  finally {
    loading.value = false
  }
}

onMounted(load)

async function setStatus(status: OrderStatus) {
  if (!admin.restaurantId || !order.value) return
  order.value = await updateOrderStatus(admin.restaurantId, order.value.id, status)
}
</script>

<template>
  <div>
    <NuxtLink to="/admin/orders" class="text-sm font-medium text-brand-700">← Back to orders</NuxtLink>

    <div v-if="loading" class="mt-6 h-48 animate-pulse rounded-2xl bg-brand-100/60" />
    <p v-else-if="error" class="mt-6 text-red-600">{{ error }}</p>

    <div v-else-if="order" class="mt-6 space-y-6">
      <section class="rounded-2xl border border-brand-100 bg-surface-elevated p-6">
        <div class="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 class="font-display text-2xl font-semibold">{{ order.order_number }}</h1>
            <p class="text-sm text-ink-muted">{{ order.customer_name }} · {{ order.customer_email }}</p>
          </div>
          <span class="rounded-full bg-brand-100 px-3 py-1 text-sm font-medium">{{ order.status.replace('_', ' ') }}</span>
        </div>
        <div class="mt-4 flex flex-wrap gap-2">
          <AppButton v-if="order.status === 'CONFIRMED'" @click="setStatus('PREPARING')">Start preparing</AppButton>
          <AppButton v-if="order.status === 'PREPARING'" @click="setStatus('READY')">Mark ready</AppButton>
          <AppButton v-if="order.status === 'READY'" @click="setStatus('COMPLETED')">Complete</AppButton>
        </div>
      </section>

      <section class="rounded-2xl border border-brand-100 bg-surface-elevated p-6">
        <h2 class="font-semibold">Items</h2>
        <ul class="mt-3 space-y-2 text-sm">
          <li v-for="item in order.items" :key="item.id" class="flex justify-between">
            <span>{{ item.quantity }}× {{ item.item_name }}</span>
            <span>{{ formatCurrency(Number(item.line_total)) }}</span>
          </li>
        </ul>
        <p class="mt-4 font-semibold">Total: {{ formatCurrency(Number(order.total)) }}</p>
      </section>
    </div>
  </div>
</template>
