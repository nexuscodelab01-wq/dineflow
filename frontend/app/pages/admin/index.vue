<script setup lang="ts">
import type { AnalyticsResponse, DateRangePreset } from '~/types/analytics'
import { exportAnalyticsCsv, fetchAnalytics } from '~/services/admin'
import { formatCurrency } from '~/utils/format'

definePageMeta({ layout: 'admin', middleware: ['staff'] })

const admin = useAdminStore()
const analytics = ref<AnalyticsResponse | null>(null)
const loading = ref(true)
const error = ref('')
const preset = ref<DateRangePreset>('last_7_days')
const startDate = ref('')
const endDate = ref('')

async function load() {
  await admin.initialize()
  if (!admin.restaurantId) return
  if (preset.value === 'custom' && (!startDate.value || !endDate.value)) {
    loading.value = false
    return
  }
  loading.value = true
  error.value = ''
  try {
    analytics.value = await fetchAnalytics(
      admin.restaurantId,
      preset.value,
      startDate.value || undefined,
      endDate.value || undefined,
    )
  }
  catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to load analytics'
  }
  finally {
    loading.value = false
  }
}

onMounted(load)

const revenueLabels = computed(() => analytics.value?.revenue_over_time.map(p => p.date.slice(5)) ?? [])
const revenueValues = computed(() => analytics.value?.revenue_over_time.map(p => Number(p.revenue)) ?? [])
const orderValues = computed(() => analytics.value?.orders_over_time.map(p => p.orders) ?? [])

const categoryLabels = computed(() => analytics.value?.orders_by_category.map(c => c.category_name) ?? [])
const categoryValues = computed(() => analytics.value?.orders_by_category.map(c => c.order_count) ?? [])

const popularLabels = computed(() => analytics.value?.popular_items.map(i => i.item_name) ?? [])
const popularValues = computed(() => analytics.value?.popular_items.map(i => i.quantity) ?? [])

const statusLabels = computed(() =>
  analytics.value?.order_status_distribution.map(s => s.status.replace('_', ' ')) ?? [],
)
const statusValues = computed(() =>
  analytics.value?.order_status_distribution.map(s => s.count) ?? [],
)

const hourLabels = computed(() => analytics.value?.sales_by_hour.map(h => `${h.hour}:00`) ?? [])
const hourValues = computed(() => analytics.value?.sales_by_hour.map(h => h.orders) ?? [])

const exporting = ref(false)
const ui = useUiStore()
async function exportCsv() {
  if (!admin.restaurantId || exporting.value) return
  exporting.value = true
  try {
    const blob = await exportAnalyticsCsv(admin.restaurantId, preset.value, startDate.value || undefined, endDate.value || undefined)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `orders-${preset.value}.csv`
    link.click()
    URL.revokeObjectURL(url)
  }
  catch (err) {
    ui.error(err instanceof Error ? err.message : 'Could not export the CSV')
  }
  finally {
    exporting.value = false
  }
}
</script>

<template>
  <div>
    <div class="flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 class="font-display text-2xl font-semibold text-brand-900">Dashboard</h1>
        <p v-if="analytics" class="mt-1 text-sm text-ink-muted">
          {{ analytics.start_date }} — {{ analytics.end_date }}
        </p>
      </div>
      <div class="flex flex-wrap items-center gap-3">
        <DateRangeFilter
          v-model:preset="preset"
          v-model:start-date="startDate"
          v-model:end-date="endDate"
          @change="load"
        />
        <button
          type="button" class="rounded-lg border border-brand-200 px-3 py-1.5 text-sm font-medium hover:bg-brand-50 disabled:opacity-50"
          :disabled="!analytics || exporting" @click="exportCsv"
        >
          {{ exporting ? 'Exporting…' : 'Export CSV' }}
        </button>
      </div>
    </div>

    <p v-if="error" class="mt-4 text-sm text-red-600">{{ error }}</p>

    <div v-if="loading" class="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-6">
      <div v-for="n in 6" :key="n" class="h-28 animate-pulse rounded-2xl bg-brand-100/60" />
    </div>

    <div v-else-if="analytics" class="mt-6 space-y-6">
      <div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-6">
        <div class="rounded-2xl border border-brand-100 bg-surface-elevated p-5">
          <p class="text-xs uppercase tracking-wide text-ink-subtle">Orders</p>
          <p class="mt-2 text-3xl font-semibold text-brand-900">{{ analytics.summary.today_orders }}</p>
        </div>
        <div class="rounded-2xl border border-brand-100 bg-surface-elevated p-5">
          <p class="text-xs uppercase tracking-wide text-ink-subtle">Revenue</p>
          <p class="mt-2 text-3xl font-semibold text-brand-900">{{ formatCurrency(Number(analytics.summary.today_revenue)) }}</p>
        </div>
        <div class="rounded-2xl border border-brand-100 bg-surface-elevated p-5">
          <p class="text-xs uppercase tracking-wide text-ink-subtle">Pending</p>
          <p class="mt-2 text-3xl font-semibold text-brand-900">{{ analytics.summary.pending_orders }}</p>
        </div>
        <div class="rounded-2xl border border-brand-100 bg-surface-elevated p-5">
          <p class="text-xs uppercase tracking-wide text-ink-subtle">Completed</p>
          <p class="mt-2 text-3xl font-semibold text-brand-900">{{ analytics.summary.completed_orders_today }}</p>
        </div>
        <div class="rounded-2xl border border-brand-100 bg-surface-elevated p-5">
          <p class="text-xs uppercase tracking-wide text-ink-subtle">Avg order</p>
          <p class="mt-2 text-3xl font-semibold text-brand-900">{{ formatCurrency(Number(analytics.summary.average_order_value)) }}</p>
        </div>
        <div class="rounded-2xl border border-brand-100 bg-surface-elevated p-5">
          <p class="text-xs uppercase tracking-wide text-ink-subtle">No-show rate</p>
          <p class="mt-2 text-3xl font-semibold text-brand-900">{{ analytics.no_show.rate }}%</p>
          <p class="mt-1 text-xs text-ink-subtle">{{ analytics.no_show.no_shows }} of {{ analytics.no_show.total_reservations }} bookings</p>
        </div>
      </div>

      <ClientOnly>
        <div class="grid gap-6 lg:grid-cols-2">
          <AnalyticsLineChart title="Revenue over time" :labels="revenueLabels" :values="revenueValues" color="#2c6f53" />
          <AnalyticsLineChart title="Orders over time" :labels="revenueLabels" :values="orderValues" color="#3a8b68" />
          <AnalyticsBarChart title="Sales by hour of day" :labels="hourLabels" :values="hourValues" color="#8a6d3b" />
          <AnalyticsBarChart title="Orders by category" :labels="categoryLabels" :values="categoryValues" color="#5aa784" />
          <AnalyticsBarChart title="Popular menu items" :labels="popularLabels" :values="popularValues" color="#255944" />
          <AnalyticsDoughnutChart
            v-if="statusLabels.length"
            title="Order status distribution"
            :labels="statusLabels"
            :values="statusValues"
          />
          <div v-else class="rounded-2xl border border-dashed border-brand-200 p-8 text-center text-sm text-ink-muted">
            No orders in this period for status breakdown.
          </div>
        </div>
      </ClientOnly>
    </div>
  </div>
</template>
