<script setup lang="ts">
import type { ShiftReportRead } from '~/types/shift'
import { fetchShifts } from '~/services/shifts'
import { formatWhen } from '~/utils/datetime'
const { money } = useMoney()

definePageMeta({ layout: 'admin', middleware: ['admin'] })

const admin = useAdminStore()

const shifts = ref<ShiftReportRead[]>([])
const loading = ref(true)
const error = ref('')

async function load() {
  if (!admin.restaurantId) return
  loading.value = true
  error.value = ''
  try {
    shifts.value = await fetchShifts(admin.restaurantId)
  }
  catch (err) {
    error.value = err instanceof Error ? err.message : 'Could not load shifts'
  }
  finally {
    loading.value = false
  }
}

onMounted(async () => {
  await admin.initialize()
  await load()
})

function variance(shift: ShiftReportRead) {
  return shift.variance === null ? null : Number(shift.variance)
}
</script>

<template>
  <div>
    <div>
      <h1 class="font-display text-2xl font-semibold text-brand-900">Shifts</h1>
      <p class="text-sm text-ink-muted">Every till shift, open or closed — starting float, cash and card taken, and the variance once counted.</p>
    </div>

    <p v-if="error" class="mt-4 text-sm text-red-600" role="alert">{{ error }}</p>
    <div v-if="loading" class="mt-6 h-32 animate-pulse rounded-2xl bg-brand-100/60" />
    <p v-else-if="!shifts.length" class="mt-6 text-sm text-ink-subtle">No shifts yet.</p>
    <ul v-else class="mt-6 space-y-3">
      <li v-for="shift in shifts" :key="shift.shift_id" class="rounded-2xl border border-brand-100 bg-surface-elevated p-4">
        <div class="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div class="flex flex-wrap items-center gap-2">
              <span class="font-semibold text-ink">{{ formatWhen(shift.opened_at) }}</span>
              <span v-if="!shift.closed_at" class="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-semibold text-emerald-900">Open</span>
              <span v-else class="rounded-full bg-brand-100 px-2 py-0.5 text-xs font-semibold text-brand-800">Closed</span>
            </div>
            <p class="mt-1 text-xs text-ink-subtle">
              Opened by {{ shift.opened_by || 'unknown' }}
              <span v-if="shift.closed_by"> · closed by {{ shift.closed_by }}</span>
            </p>
          </div>
          <div v-if="variance(shift) !== null" class="text-right">
            <p class="text-xs uppercase tracking-wide text-ink-subtle">Variance</p>
            <p :class="variance(shift) === 0 ? 'text-emerald-700' : 'text-red-600'" class="text-lg font-semibold">
              {{ money(variance(shift)!) }}
            </p>
          </div>
        </div>
        <div class="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-6">
          <div>
            <p class="text-xs uppercase tracking-wide text-ink-subtle">Starting float</p>
            <p class="font-semibold text-ink">{{ money(Number(shift.starting_float)) }}</p>
          </div>
          <div>
            <p class="text-xs uppercase tracking-wide text-ink-subtle">Cash</p>
            <p class="font-semibold text-ink">{{ money(Number(shift.cash_total)) }}</p>
          </div>
          <div>
            <p class="text-xs uppercase tracking-wide text-ink-subtle">Card</p>
            <p class="font-semibold text-ink">{{ money(Number(shift.card_total)) }}</p>
          </div>
          <div v-if="Number(shift.card_tips) || Number(shift.cash_tips)">
            <p class="text-xs uppercase tracking-wide text-ink-subtle">Tips (card · cash)</p>
            <p class="font-semibold text-ink">{{ money(Number(shift.card_tips)) }} · {{ money(Number(shift.cash_tips)) }}</p>
          </div>
          <div>
            <p class="text-xs uppercase tracking-wide text-ink-subtle">Orders</p>
            <p class="font-semibold text-ink">{{ shift.order_count }}</p>
          </div>
          <div>
            <p class="text-xs uppercase tracking-wide text-ink-subtle">Counted cash</p>
            <p class="font-semibold text-ink">{{ shift.counted_cash === null ? '—' : money(Number(shift.counted_cash)) }}</p>
          </div>
        </div>
      </li>
    </ul>
  </div>
</template>
