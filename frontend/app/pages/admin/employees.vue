<script setup lang="ts">
import type { DateRangePreset } from '~/types/analytics'
import type { EmployeeReportRow } from '~/types/shift'
import { fetchEmployeeReport } from '~/services/employees'
const { money } = useMoney()

definePageMeta({ layout: 'admin', middleware: ['admin'] })

const admin = useAdminStore()

const rows = ref<EmployeeReportRow[]>([])
const loading = ref(true)
const error = ref('')
const preset = ref<DateRangePreset>('last_7_days')
const startDate = ref('')
const endDate = ref('')

async function load() {
  if (!admin.restaurantId) return
  if (preset.value === 'custom' && (!startDate.value || !endDate.value)) {
    loading.value = false
    return
  }
  loading.value = true
  error.value = ''
  try {
    rows.value = await fetchEmployeeReport(admin.restaurantId, preset.value, startDate.value || undefined, endDate.value || undefined)
  }
  catch (err) {
    error.value = err instanceof Error ? err.message : 'Could not load the employee report'
  }
  finally {
    loading.value = false
  }
}

onMounted(async () => {
  await admin.initialize()
  await load()
})
</script>

<template>
  <div>
    <div class="flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 class="font-display text-2xl font-semibold text-brand-900">Employees</h1>
        <p class="text-sm text-ink-muted">Cash and card taken, orders handled, and hours worked — per staff member who took a POS payment.</p>
      </div>
      <DateRangeFilter v-model:preset="preset" v-model:start-date="startDate" v-model:end-date="endDate" @change="load" />
    </div>

    <p v-if="error" class="mt-4 text-sm text-red-600" role="alert">{{ error }}</p>
    <div v-if="loading" class="mt-6 h-32 animate-pulse rounded-2xl bg-brand-100/60" />
    <p v-else-if="!rows.length" class="mt-6 text-sm text-ink-subtle">No staff payments in this range.</p>
    <ul v-else class="mt-6 space-y-3">
      <li v-for="row in rows" :key="row.user_id" class="rounded-2xl border border-brand-100 bg-surface-elevated p-4">
        <p class="font-semibold text-ink">{{ row.name }}</p>
        <div class="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-5">
          <div>
            <p class="text-xs uppercase tracking-wide text-ink-subtle">Cash</p>
            <p class="font-semibold text-ink">{{ money(Number(row.cash_total)) }}</p>
          </div>
          <div>
            <p class="text-xs uppercase tracking-wide text-ink-subtle">Card</p>
            <p class="font-semibold text-ink">{{ money(Number(row.card_total)) }}</p>
          </div>
          <div>
            <p class="text-xs uppercase tracking-wide text-ink-subtle">Orders</p>
            <p class="font-semibold text-ink">{{ row.order_count }}</p>
          </div>
          <div>
            <p class="text-xs uppercase tracking-wide text-ink-subtle">Hours worked</p>
            <p class="font-semibold text-ink">{{ Number(row.hours_worked).toFixed(2) }}</p>
          </div>
          <div>
            <p class="text-xs uppercase tracking-wide text-ink-subtle">Sales / labour hour</p>
            <p class="font-semibold text-ink">{{ row.sales_per_labour_hour === null ? '—' : money(Number(row.sales_per_labour_hour)) }}</p>
          </div>
        </div>
      </li>
    </ul>
  </div>
</template>
