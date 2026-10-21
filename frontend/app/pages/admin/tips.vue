<script setup lang="ts">
import type { TipAllocation, TipReport } from '~/types/tips'
import { fetchTipHistory, fetchTipReport, finalizeTips } from '~/services/tips'
import { formatWhen } from '~/utils/datetime'

definePageMeta({ layout: 'admin', middleware: ['admin'] })

const { money } = useMoney()
const admin = useAdminStore()

// A period is a pair of local date-times; default to the last 7 days.
function localInput(d: Date) {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}
const end = ref(localInput(new Date()))
const start = ref(localInput(new Date(Date.now() - 7 * 24 * 3600 * 1000)))

const report = ref<TipReport | null>(null)
const history = ref<TipAllocation[]>([])
const loading = ref(false)
const finalizing = ref(false)
const error = ref('')
const message = ref('')

const modeLabel: Record<string, string> = {
  KEEP: 'Each person keeps their own tips',
  POOL_EQUAL: 'Pooled and split equally',
  POOL_HOURS: 'Pooled and split by hours worked',
}

const iso = (local: string) => new Date(local).toISOString()

async function load() {
  if (!admin.restaurantId) return
  loading.value = true
  error.value = ''
  message.value = ''
  try {
    report.value = await fetchTipReport(admin.restaurantId, iso(start.value), iso(end.value))
    history.value = await fetchTipHistory(admin.restaurantId)
  }
  catch (err) {
    error.value = err instanceof Error ? err.message : 'Could not load tips'
  }
  finally {
    loading.value = false
  }
}

async function finalize() {
  if (!admin.restaurantId || !report.value) return
  if (!window.confirm('Finalize this period? It is written to the tip ledger and cannot be changed.')) return
  finalizing.value = true
  error.value = ''
  try {
    report.value = await finalizeTips(admin.restaurantId, iso(start.value), iso(end.value))
    history.value = await fetchTipHistory(admin.restaurantId)
    message.value = 'Period finalized and recorded.'
  }
  catch (err) {
    error.value = err instanceof Error ? err.message : 'Could not finalize'
  }
  finally {
    finalizing.value = false
  }
}

onMounted(async () => {
  await admin.initialize()
  await load()
})
</script>

<template>
  <div>
    <h1 class="font-display text-2xl font-semibold text-brand-900">Tips</h1>
    <p class="text-sm text-ink-muted">Card tips from the reader plus cash tips staff declared, and what each person is paid under your pooling policy.</p>

    <form class="mt-5 flex flex-wrap items-end gap-3" @submit.prevent="load">
      <label class="text-sm">From<input v-model="start" type="datetime-local" class="mt-1 block rounded-lg border px-3 py-2 text-sm"></label>
      <label class="text-sm">To<input v-model="end" type="datetime-local" class="mt-1 block rounded-lg border px-3 py-2 text-sm"></label>
      <AppButton type="submit" :disabled="loading">{{ loading ? 'Loading…' : 'Show' }}</AppButton>
    </form>

    <p v-if="error" class="mt-4 text-sm text-red-600" role="alert">{{ error }}</p>
    <p v-if="message" class="mt-4 text-sm text-emerald-700">{{ message }}</p>

    <section v-if="report" class="mt-6 rounded-2xl border border-brand-100 bg-surface-elevated p-5">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p class="font-semibold text-ink">{{ modeLabel[report.mode] }}</p>
          <p class="text-sm text-ink-muted">Total tips in this period: <strong>{{ money(Number(report.total)) }}</strong></p>
        </div>
        <AppButton v-if="report.rows.length && !report.already_finalized" :disabled="finalizing" @click="finalize">
          {{ finalizing ? 'Saving…' : 'Finalize period' }}
        </AppButton>
        <span v-else-if="report.already_finalized" class="rounded-full bg-brand-100 px-2 py-0.5 text-xs font-semibold text-brand-800">Finalized</span>
      </div>
      <p v-if="!report.rows.length" class="mt-4 text-sm text-ink-subtle">No tips in this period.</p>
      <div v-else class="mt-4 overflow-x-auto">
        <table class="w-full text-left text-sm">
          <thead class="text-xs uppercase tracking-wide text-ink-subtle">
            <tr><th class="py-2 pr-4">Staff</th><th class="pr-4">Card</th><th class="pr-4">Cash</th><th class="pr-4">Collected</th><th class="pr-4">Hours</th><th>Paid out</th></tr>
          </thead>
          <tbody>
            <tr v-for="row in report.rows" :key="row.user_id" class="border-t border-brand-100">
              <td class="py-2 pr-4 font-medium text-ink">{{ row.name }}</td>
              <td class="pr-4">{{ money(Number(row.card_tips)) }}</td>
              <td class="pr-4">{{ money(Number(row.cash_tips)) }}</td>
              <td class="pr-4">{{ money(Number(row.collected)) }}</td>
              <td class="pr-4">{{ Number(row.hours).toFixed(2) }}</td>
              <td class="font-semibold text-ink">{{ money(Number(row.payout)) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section v-if="history.length" class="mt-8">
      <h2 class="font-semibold text-ink">Tip ledger</h2>
      <p class="text-xs text-ink-subtle">Every finalized payout, kept as a permanent record.</p>
      <div class="mt-3 overflow-x-auto rounded-2xl border border-brand-100 bg-surface-elevated">
        <table class="w-full text-left text-sm">
          <thead class="text-xs uppercase tracking-wide text-ink-subtle">
            <tr><th class="p-3">Period</th><th class="pr-4">Staff</th><th class="pr-4">Policy</th><th class="pr-4">Collected</th><th class="pr-4">Paid</th><th>Recorded</th></tr>
          </thead>
          <tbody>
            <tr v-for="h in history" :key="h.id" class="border-t border-brand-100">
              <td class="p-3">{{ formatWhen(h.period_start) }} – {{ formatWhen(h.period_end) }}</td>
              <td class="pr-4">{{ h.name }}</td>
              <td class="pr-4">{{ h.mode }}</td>
              <td class="pr-4">{{ money(Number(h.collected)) }}</td>
              <td class="pr-4 font-semibold">{{ money(Number(h.amount)) }}</td>
              <td>{{ formatWhen(h.created_at) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>
