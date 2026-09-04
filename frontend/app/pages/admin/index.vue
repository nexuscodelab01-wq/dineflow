<script setup lang="ts">
import type { DashboardStats } from '~/types/admin'
import { fetchDashboard } from '~/services/admin'
import { formatCurrency } from '~/utils/format'

definePageMeta({ layout: 'admin', middleware: ['staff'] })

const admin = useAdminStore()
const stats = ref<DashboardStats | null>(null)
const loading = ref(true)
const error = ref('')

async function load() {
  await admin.initialize()
  if (!admin.restaurantId) return
  loading.value = true
  error.value = ''
  try {
    stats.value = await fetchDashboard(admin.restaurantId)
  }
  catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to load dashboard'
  }
  finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div>
    <h1 class="font-display text-2xl font-semibold text-brand-900">Dashboard</h1>
    <p class="mt-1 text-sm text-ink-muted">Today’s restaurant overview</p>

    <p v-if="error" class="mt-4 text-sm text-red-600">{{ error }}</p>

    <div v-if="loading" class="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
      <div v-for="n in 5" :key="n" class="h-24 animate-pulse rounded-2xl bg-brand-100/60" />
    </div>

    <div v-else-if="stats" class="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
      <div class="rounded-2xl border border-brand-100 bg-surface-elevated p-4">
        <p class="text-xs font-medium uppercase tracking-wide text-ink-subtle">Orders today</p>
        <p class="mt-2 text-2xl font-semibold text-brand-900">{{ stats.today_orders }}</p>
      </div>
      <div class="rounded-2xl border border-brand-100 bg-surface-elevated p-4">
        <p class="text-xs font-medium uppercase tracking-wide text-ink-subtle">Revenue today</p>
        <p class="mt-2 text-2xl font-semibold text-brand-900">{{ formatCurrency(Number(stats.today_revenue)) }}</p>
      </div>
      <div class="rounded-2xl border border-brand-100 bg-surface-elevated p-4">
        <p class="text-xs font-medium uppercase tracking-wide text-ink-subtle">Pending</p>
        <p class="mt-2 text-2xl font-semibold text-brand-900">{{ stats.pending_orders }}</p>
      </div>
      <div class="rounded-2xl border border-brand-100 bg-surface-elevated p-4">
        <p class="text-xs font-medium uppercase tracking-wide text-ink-subtle">Completed today</p>
        <p class="mt-2 text-2xl font-semibold text-brand-900">{{ stats.completed_orders_today }}</p>
      </div>
      <div class="rounded-2xl border border-brand-100 bg-surface-elevated p-4">
        <p class="text-xs font-medium uppercase tracking-wide text-ink-subtle">Avg order value</p>
        <p class="mt-2 text-2xl font-semibold text-brand-900">{{ formatCurrency(Number(stats.average_order_value)) }}</p>
      </div>
    </div>

    <div class="mt-8 flex flex-wrap gap-3">
      <NuxtLink to="/admin/orders" class="rounded-lg bg-brand-700 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-800">
        View orders
      </NuxtLink>
      <NuxtLink to="/admin/menu" class="rounded-lg border border-brand-200 px-4 py-2 text-sm font-semibold text-brand-800 hover:bg-brand-50">
        Manage menu
      </NuxtLink>
    </div>
  </div>
</template>
