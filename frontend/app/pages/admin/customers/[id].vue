<script setup lang="ts">
import type { Order } from '~/types/order'
import { fetchAdminCustomer } from '~/services/admin'
import { formatCurrency } from '~/utils/format'

definePageMeta({ layout: 'admin', middleware: ['staff'] })

const route = useRoute()
const admin = useAdminStore()
const detail = ref<{ user_id: number; total_orders: number; total_spending: string; orders: Order[] } | null>(null)
const loading = ref(true)

onMounted(async () => {
  await admin.initialize()
  if (admin.restaurantId) {
    detail.value = await fetchAdminCustomer(admin.restaurantId, Number(route.params.id))
  }
  loading.value = false
})
</script>

<template>
  <div>
    <NuxtLink to="/admin/customers" class="text-sm font-medium text-brand-700">← Customers</NuxtLink>

    <div v-if="loading" class="mt-6 h-40 animate-pulse rounded-2xl bg-brand-100/60" />

    <div v-else-if="detail" class="mt-6 space-y-6">
      <section class="rounded-2xl border border-brand-100 bg-surface-elevated p-6">
        <h1 class="font-display text-2xl font-semibold">Customer #{{ detail.user_id }}</h1>
        <p class="mt-2 text-sm text-ink-muted">{{ detail.total_orders }} orders · {{ formatCurrency(Number(detail.total_spending)) }} total</p>
      </section>

      <section class="rounded-2xl border border-brand-100 bg-surface-elevated p-6">
        <h2 class="font-semibold">Order history</h2>
        <ul class="mt-4 space-y-3">
          <li v-for="order in detail.orders" :key="order.id" class="flex justify-between text-sm">
            <span>{{ order.order_number }} · {{ new Date(order.created_at).toLocaleDateString() }}</span>
            <span>{{ formatCurrency(Number(order.total)) }}</span>
          </li>
        </ul>
      </section>
    </div>
  </div>
</template>
