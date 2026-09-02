<script setup lang="ts">
import type { Order } from '~/types/order'
import { fetchOrder } from '~/services/orders'
import { formatCurrency } from '~/utils/format'

definePageMeta({ middleware: ['auth'] })

const route = useRoute()
const orderId = computed(() => Number(route.params.id))
const order = ref<Order | null>(null)
const loading = ref(true)
const error = ref('')

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

onMounted(loadOrder)

// Refresh every 30s for live tracking
const { pause } = useIntervalFn(loadOrder, 30000)
onUnmounted(pause)
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

      <section class="rounded-2xl border border-brand-100 bg-surface-elevated p-6">
        <h2 class="font-semibold text-ink">Progress</h2>
        <div class="mt-4">
          <OrderProgressTracker :status="order.status" />
        </div>
      </section>

      <section class="rounded-2xl border border-brand-100 bg-surface-elevated p-6">
        <h2 class="font-semibold text-ink">Items</h2>
        <ul class="mt-4 space-y-3">
          <li v-for="item in order.items" :key="item.id" class="flex justify-between gap-4 text-sm">
            <div>
              <p class="font-medium text-ink">{{ item.quantity }}× {{ item.item_name }}</p>
              <ul v-if="item.modifiers.length" class="mt-1 text-ink-muted">
                <li v-for="mod in item.modifiers" :key="mod.id">{{ mod.modifier_name }}: {{ mod.option_name }}</li>
              </ul>
            </div>
            <span>{{ formatCurrency(Number(item.line_total)) }}</span>
          </li>
        </ul>
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
