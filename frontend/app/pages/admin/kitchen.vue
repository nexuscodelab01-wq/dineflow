<script setup lang="ts">
import { useDebounceFn, useIntervalFn } from '@vueuse/core'
import type { KitchenBoard } from '~/types/admin'
import type { Order, OrderStatus } from '~/types/order'
import { fetchKitchenBoard, updateOrderStatus } from '~/services/admin'
import { subscribeKitchen } from '~/services/realtime'
import type { SseStatus } from '~/utils/sse'

definePageMeta({ layout: 'admin', middleware: ['staff'] })

const admin = useAdminStore()
const ui = useUiStore()
const board = ref<KitchenBoard | null>(null)
const loading = ref(true)
const connection = ref<SseStatus>('connecting')

async function load() {
  await admin.initialize()
  if (!admin.restaurantId) return
  try {
    board.value = await fetchKitchenBoard(admin.restaurantId)
  }
  catch (err) {
    if (loading.value) ui.error(err instanceof Error ? err.message : 'Could not load orders')
  }
  finally {
    loading.value = false
  }
}

// Several events can arrive together (an order plus its status change): refetch once.
const refreshSoon = useDebounceFn(load, 250)

let stream: { close: () => void } | null = null

onMounted(async () => {
  await load()
  if (!admin.restaurantId) return
  stream = subscribeKitchen(admin.restaurantId, {
    onChange: refreshSoon,
    onStatus: (status) => {
      connection.value = status
    },
  })
  document.addEventListener('visibilitychange', onVisible)
})

onBeforeUnmount(() => {
  stream?.close()
  document.removeEventListener('visibilitychange', onVisible)
})

// A tablet that slept or a background tab may have missed events: catch up when it wakes.
function onVisible() {
  if (document.visibilityState === 'visible') load()
}

// Safety net: rarely while the live stream is healthy, often when it is not.
useIntervalFn(load, computed(() => (connection.value === 'live' ? 60000 : 15000)))

async function advance(order: Order, status: OrderStatus) {
  if (!admin.restaurantId) return
  try {
    await updateOrderStatus(admin.restaurantId, order.id, status)
    await load()
  }
  catch (err) {
    ui.error(err instanceof Error ? err.message : 'Could not update the order')
    await load()
  }
}

function nextStatus(order: Order): OrderStatus | null {
  if (order.status === 'CONFIRMED') return 'PREPARING'
  if (order.status === 'PREPARING') return 'READY'
  if (order.status === 'READY') return 'COMPLETED'
  return null
}
</script>

<template>
  <div>
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="font-display text-2xl font-semibold text-brand-900">Kitchen display</h1>
        <p class="text-sm text-ink-muted">Orders appear the moment they are placed.</p>
      </div>
      <span
        class="inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-semibold"
        :class="connection === 'live' ? 'bg-emerald-100 text-emerald-900' : 'bg-amber-100 text-amber-900'"
        role="status"
        data-testid="connection-status"
      >
        <span class="h-2 w-2 rounded-full" :class="connection === 'live' ? 'bg-emerald-500' : 'animate-pulse bg-amber-500'" />
        {{ connection === 'live' ? 'Live' : connection === 'closed' ? 'Offline — refreshing every 15s' : 'Reconnecting…' }}
      </span>
    </div>

    <div v-if="loading" class="mt-6 h-64 animate-pulse rounded-2xl bg-brand-100/60" />

    <div v-else-if="board" class="mt-6 grid gap-4 lg:grid-cols-3">
      <section v-for="(column, key) in { New: board.new_orders, Preparing: board.preparing, Ready: board.ready }" :key="key" class="rounded-2xl border border-brand-100 bg-surface-elevated p-4">
        <h2 class="mb-4 font-semibold text-brand-900">{{ key }} ({{ column.length }})</h2>
        <div class="space-y-3">
          <article v-for="order in column" :key="order.id" class="rounded-xl border border-brand-100 bg-brand-50/40 p-4">
            <p class="font-semibold">{{ order.order_number }}</p>
            <ul class="mt-2 space-y-1 text-sm text-ink-muted">
              <li v-for="item in order.items" :key="item.id">{{ item.quantity }}× {{ item.item_name }}</li>
            </ul>
            <AppButton
              v-if="nextStatus(order)"
              class="mt-3 w-full"
              @click="advance(order, nextStatus(order)!)"
            >
              → {{ nextStatus(order)!.replace('_', ' ') }}
            </AppButton>
          </article>
          <p v-if="!column.length" class="text-sm text-ink-subtle">No orders</p>
        </div>
      </section>
    </div>
  </div>
</template>
