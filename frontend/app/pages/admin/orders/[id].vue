<script setup lang="ts">
import type { Order, OrderStatus } from '~/types/order'
import { fetchAdminOrder, updateOrderStatus } from '~/services/admin'
import { formatCurrency } from '~/utils/format'

definePageMeta({ layout: 'admin', middleware: ['staff'] })

const route = useRoute()
const admin = useAdminStore()
const ui = useUiStore()
const order = ref<Order | null>(null)
const loading = ref(true)
const error = ref('')
const cancelling = ref(false)

const orderId = computed(() => Number(route.params.id))
// Mirrors STAFF_ALLOWED_TRANSITIONS on the backend — everything but a terminal state can still be cancelled.
const cancellable = computed(() => !!order.value && !['CANCELLED', 'COMPLETED', 'DELIVERED'].includes(order.value.status))

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

async function cancelOrder() {
  if (!admin.restaurantId || !order.value) return
  const paid = order.value.payments.some((p: { status: string }) => p.status === 'COMPLETED')
  const ok = await ui.confirm({
    title: 'Cancel this order?',
    message: paid
      ? 'The customer already paid — this refunds their card in full and cannot be undone.'
      : 'This cannot be undone.',
    confirmLabel: 'Cancel order',
    destructive: true,
  })
  if (!ok) return
  cancelling.value = true
  try {
    order.value = await updateOrderStatus(admin.restaurantId, order.value.id, 'CANCELLED')
    ui.success(paid ? 'Order cancelled and refunded' : 'Order cancelled')
  }
  catch (err) {
    ui.error(err instanceof Error ? err.message : 'Could not cancel the order')
  }
  finally {
    cancelling.value = false
  }
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
          <button
            v-if="cancellable"
            class="rounded-lg border border-red-300 px-4 py-2 text-sm font-semibold text-red-700 hover:bg-red-50 disabled:opacity-60"
            :disabled="cancelling"
            @click="cancelOrder"
          >
            {{ cancelling ? 'Cancelling…' : 'Cancel order' }}
          </button>
        </div>
      </section>

      <section class="rounded-2xl border border-brand-100 bg-surface-elevated p-6">
        <h2 class="font-semibold">Items</h2>
        <OrderItemList class="mt-3" :items="order.items" show-prices />
        <p v-if="order.notes" class="mt-4 rounded-md border border-amber-300 bg-amber-100 px-3 py-2 text-sm font-semibold text-amber-950">
          <span class="mr-1 uppercase tracking-wide">Order note:</span>{{ order.notes }}
        </p>
        <p v-if="order.payments.length" class="mt-4 text-sm text-ink-muted">Payment: {{ order.payments[0].status }}</p>
        <p class="mt-4 font-semibold">Total: {{ formatCurrency(Number(order.total)) }}</p>
      </section>
    </div>
  </div>
</template>
