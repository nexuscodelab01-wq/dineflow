<script setup lang="ts">
import type { Adjustment } from '~/types/adjustment'
import { fetchAdjustments } from '~/services/adjustments'
import { formatWhen } from '~/utils/datetime'

definePageMeta({ layout: 'admin', middleware: ['admin'] })

const { money } = useMoney()
const admin = useAdminStore()

function localInput(d: Date) {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}
const end = ref(localInput(new Date()))
const start = ref(localInput(new Date(Date.now() - 7 * 24 * 3600 * 1000)))
const kind = ref<'ALL' | Adjustment['kind']>('ALL')
const rows = ref<Adjustment[]>([])
const loading = ref(false)
const error = ref('')

const shown = computed(() => rows.value.filter(r => kind.value === 'ALL' || r.kind === kind.value))
const total = computed(() => shown.value.reduce((sum, r) => sum + Number(r.amount), 0))
const label: Record<string, string> = { VOID: 'Void', COMP: 'Comp', DISCOUNT: 'Discount', REFUND: 'Refund' }

async function load() {
  if (!admin.restaurantId) return
  loading.value = true
  error.value = ''
  try {
    rows.value = await fetchAdjustments(admin.restaurantId, new Date(start.value).toISOString(), new Date(end.value).toISOString())
  }
  catch (err) {
    error.value = err instanceof Error ? err.message : 'Could not load the report'
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
    <h1 class="font-display text-2xl font-semibold text-brand-900">Voids &amp; refunds</h1>
    <p class="text-sm text-ink-muted">Every void, comp, discount and refund taken at the POS — who did it, why, and who approved it.</p>

    <form class="mt-5 flex flex-wrap items-end gap-3" @submit.prevent="load">
      <label class="text-sm">From<input v-model="start" type="datetime-local" class="mt-1 block rounded-lg border px-3 py-2 text-sm"></label>
      <label class="text-sm">To<input v-model="end" type="datetime-local" class="mt-1 block rounded-lg border px-3 py-2 text-sm"></label>
      <label class="text-sm">Type
        <select v-model="kind" class="mt-1 block rounded-lg border px-3 py-2 text-sm">
          <option value="ALL">All</option>
          <option v-for="(l, k) in label" :key="k" :value="k">{{ l }}</option>
        </select>
      </label>
      <AppButton type="submit" :disabled="loading">{{ loading ? 'Loading…' : 'Show' }}</AppButton>
    </form>

    <p v-if="error" class="mt-4 text-sm text-red-600" role="alert">{{ error }}</p>
    <p v-else-if="!loading && !shown.length" class="mt-6 text-sm text-ink-subtle">Nothing in this period.</p>
    <div v-else-if="shown.length" class="mt-6">
      <p class="text-sm text-ink-muted">{{ shown.length }} entries · <strong>{{ money(total) }}</strong> in total</p>
      <div class="mt-3 overflow-x-auto rounded-2xl border border-brand-100 bg-surface-elevated">
        <table class="w-full text-left text-sm">
          <thead class="text-xs uppercase tracking-wide text-ink-subtle">
            <tr><th class="p-3">When</th><th class="pr-4">Type</th><th class="pr-4">Amount</th><th class="pr-4">Order</th><th class="pr-4">Reason</th><th class="pr-4">By</th><th>Approved by</th></tr>
          </thead>
          <tbody>
            <tr v-for="r in shown" :key="r.id" class="border-t border-brand-100 align-top">
              <td class="p-3">{{ formatWhen(r.created_at) }}</td>
              <td class="pr-4 font-medium">{{ label[r.kind] }}</td>
              <td class="pr-4">{{ money(Number(r.amount)) }}</td>
              <td class="pr-4">{{ r.order_number || '—' }}</td>
              <td class="pr-4">{{ r.reason_code.replace(/_/g, ' ').toLowerCase() }}<span v-if="r.note" class="block text-xs text-ink-subtle">{{ r.note }}</span></td>
              <td class="pr-4">{{ r.staff || '—' }}</td>
              <td>{{ r.authorized_by || '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
