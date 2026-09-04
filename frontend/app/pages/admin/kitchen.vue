<script setup lang="ts">
import type { KitchenBoard } from '~/types/admin'
import type { Order, OrderStatus } from '~/types/order'
import { fetchKitchenBoard, updateOrderStatus } from '~/services/admin'

definePageMeta({ layout: 'admin', middleware: ['staff'] })

const admin = useAdminStore()
const board = ref<KitchenBoard | null>(null)
const loading = ref(true)

async function load() {
  await admin.initialize()
  if (!admin.restaurantId) return
  board.value = await fetchKitchenBoard(admin.restaurantId)
  loading.value = false
}

onMounted(load)
const { pause } = useIntervalFn(load, 15000)
onUnmounted(pause)

async function advance(order: Order, status: OrderStatus) {
  if (!admin.restaurantId) return
  await updateOrderStatus(admin.restaurantId, order.id, status)
  await load()
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
    <h1 class="font-display text-2xl font-semibold text-brand-900">Kitchen display</h1>
    <p class="text-sm text-ink-muted">Live order queue — refreshes every 15s</p>

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
