<script setup lang="ts">
import { useIntervalFn } from '@vueuse/core'
import type { Order } from '~/types/order'
import { fetchOrder } from '~/services/orders'
import { subscribeOrder } from '~/services/realtime'
import { formatCurrency } from '~/utils/format'

definePageMeta({ middleware: ['auth'] })

const reviewsEnabled = useFeature('reviews')
const route = useRoute()
const orderId = computed(() => Number(route.params.id))
const order = ref<Order | null>(null)
const loading = ref(true)
const error = ref('')
const isDone = computed(() => order.value?.status === 'COMPLETED' || order.value?.status === 'DELIVERED')

async function loadOrder() {
  loading.value = true
  error.value = ''
  try {
    order.value = await fetchOrder(orderId.value)
  }
  catch (err) {
    error.value = err instanceof Error ? err.message : 'Order not found'
  }
  finally {
    loading.value = false
  }
}

// Status changes arrive instantly over a live connection; the slow poll only covers a connection that has dropped.
let live: { close: () => void } | null = null
onMounted(() => {
  void loadOrder()
  live = subscribeOrder(Number(route.params.id), { onChange: () => void loadOrder() })
})

const { pause } = useIntervalFn(loadOrder, 60000)
onUnmounted(() => {
  pause()
  live?.close()
})
</script>

<template>
  <div class="mx-auto max-w-3xl px-4 py-8 sm:px-6">
    <NuxtLink to="/orders" class="text-sm font-medium text-brand-700 hover:text-brand-800">← All orders</NuxtLink>

    <div v-if="loading && !order" class="mt-8 h-80 animate-pulse rounded-2xl bg-brand-100/60" />

    <p v-else-if="error" class="mt-6 text-sm text-red-600">{{ error }}</p>

    <div v-else-if="order" class="mt-6 space-y-6">
      <section class="rounded-2xl border border-brand-100 bg-surface-elevated p-6">
        <div class="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 class="font-display text-2xl font-semibold text-brand-900">{{ order.order_number }}</h1>
            <p class="mt-1 text-sm text-ink-muted">Placed {{ new Date(order.created_at).toLocaleString() }}</p>
          </div>
          <span class="rounded-full bg-brand-100 px-3 py-1 text-sm font-medium text-brand-800">
            {{ order.status.replace('_', ' ') }}
          </span>
        </div>
      </section>

      <section
        v-if="reviewsEnabled && isDone"
        class="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-brand-200 bg-brand-50 p-5"
      >
        <p class="text-sm font-medium text-ink">How was it? Let us know what you thought.</p>
        <NuxtLink
          to="/reviews"
          class="inline-flex items-center rounded-full bg-brand-700 px-5 py-2 text-sm font-semibold text-white transition hover:bg-brand-800"
        >
          Leave a review
        </NuxtLink>
      </section>

      <section class="rounded-2xl border border-brand-100 bg-surface-elevated p-6">
        <h2 class="font-semibold text-ink">Progress</h2>
        <div class="mt-4">
          <OrderProgressTracker :status="order.status" />
        </div>
      </section>

      <section class="rounded-2xl border border-brand-100 bg-surface-elevated p-6">
        <h2 class="font-semibold text-ink">Items</h2>
        <OrderItemList class="mt-4" :items="order.items" show-prices />
        <div class="mt-4 space-y-1 border-t border-brand-100 pt-4 text-sm">
          <div class="flex justify-between"><span>Subtotal</span><span>{{ formatCurrency(Number(order.subtotal)) }}</span></div>
          <div class="flex justify-between"><span>Tax</span><span>{{ formatCurrency(Number(order.tax)) }}</span></div>
          <div v-if="Number(order.delivery_fee)" class="flex justify-between"><span>Delivery</span><span>{{ formatCurrency(Number(order.delivery_fee)) }}</span></div>
          <div class="flex justify-between font-semibold"><span>Total</span><span>{{ formatCurrency(Number(order.total)) }}</span></div>
        </div>
      </section>
    </div>
  </div>
</template>
