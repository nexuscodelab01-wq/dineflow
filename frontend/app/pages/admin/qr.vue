<script setup lang="ts">
import QRCode from 'qrcode'
import type { OpenTableSession, QrTable } from '~/types/table'
import { closeSession, fetchOpenSessions, fetchQrTables, rotateQr } from '~/services/table'
import { formatCurrency } from '~/utils/format'

definePageMeta({ layout: 'admin', middleware: ['staff'] })

const admin = useAdminStore()
const auth = useAuthStore()
const ui = useUiStore()
const branding = useBranding()
const restaurantSite = useRestaurantStore()

const enabled = useFeature('qr_table_ordering')
const sessions = ref<OpenTableSession[]>([])
const tables = ref<QrTable[]>([])
const images = ref<Record<number, string>>({})
const loading = ref(true)
const error = ref('')
const busy = ref<number | null>(null)

const origin = ref('')
const linkFor = (t: QrTable) => `${origin.value}/t/${t.qr_token}`
const printTents = () => window.print()

async function draw(list: QrTable[]) {
  for (const t of list) images.value[t.table_id] = await QRCode.toDataURL(linkFor(t), { margin: 1, width: 480, errorCorrectionLevel: 'M' })
}

async function load() {
  await admin.initialize()
  const rid = admin.restaurantId
  if (!rid) return void (loading.value = false)
  try {
    sessions.value = await fetchOpenSessions(rid)
    if (auth.isAdmin) {
      tables.value = await fetchQrTables(rid)
      await draw(tables.value)
    }
    error.value = ''
  }
  catch (err) {
    error.value = err instanceof Error ? err.message : 'Could not load table ordering'
  }
  finally {
    loading.value = false
  }
}

onMounted(() => {
  origin.value = window.location.origin
  void load()
  timer = setInterval(() => { if (document.visibilityState === 'visible') refreshSessions() }, 8000)
})
let timer: ReturnType<typeof setInterval> | null = null
onUnmounted(() => { if (timer) clearInterval(timer) })

async function refreshSessions() {
  if (!admin.restaurantId) return
  try {
    sessions.value = await fetchOpenSessions(admin.restaurantId)
  }
  catch { /* the next tick will try again */ }
}

async function close(session: OpenTableSession) {
  if (!admin.restaurantId) return
  if (!window.confirm(`Close Table ${session.table_number}'s tab? Guests will no longer be able to order, and the table's QR code is replaced.`)) return
  busy.value = session.session_id
  try {
    await closeSession(admin.restaurantId, session.session_id)
    ui.success(`Table ${session.table_number} closed`)
    await load()
  }
  catch (err) {
    ui.error(err instanceof Error ? err.message : 'Could not close the tab')
  }
  finally {
    busy.value = null
  }
}

async function replace(table: QrTable) {
  if (!admin.restaurantId) return
  if (!window.confirm(`Replace Table ${table.table_number}'s QR code? The printed one will stop working.`)) return
  busy.value = table.table_id
  try {
    const fresh = await rotateQr(admin.restaurantId, table.table_id)
    tables.value = tables.value.map(t => (t.table_id === fresh.table_id ? fresh : t))
    await draw([fresh])
    ui.success('New code ready. Print it again.')
  }
  catch (err) {
    ui.error(err instanceof Error ? err.message : 'Could not replace the code')
  }
  finally {
    busy.value = null
  }
}

const printName = computed(() => branding.name.value ?? restaurantSite.current?.name ?? 'Scan to order')
</script>

<template>
  <div>
    <div class="print:hidden">
      <h1 class="font-display text-3xl font-semibold text-brand-900">Table ordering</h1>
      <p class="mt-1 text-ink-muted">Guests scan a table's code, order from their phone and share one tab.</p>

      <p v-if="!enabled" class="mt-6 rounded-xl bg-amber-50 p-4 text-amber-900">Table ordering isn't switched on for this restaurant.</p>
      <p v-else-if="loading" class="mt-6 text-ink-muted">Loading…</p>
      <p v-else-if="error" class="mt-6 rounded-xl bg-red-50 p-4 text-red-700">{{ error }}</p>

      <template v-else>
        <section class="mt-6">
          <h2 class="text-lg font-semibold">Open tabs</h2>
          <p v-if="!sessions.length" class="mt-2 text-sm text-ink-muted">No table is ordering right now. Guests can order once you mark their table as occupied.</p>
          <ul v-else class="mt-3 grid gap-3 sm:grid-cols-2">
            <li v-for="s in sessions" :key="s.session_id" class="rounded-xl border border-brand-100 bg-surface-elevated p-4">
              <div class="flex items-center justify-between">
                <h3 class="font-semibold">Table {{ s.table_number }}</h3>
                <span class="text-sm text-ink-muted">{{ s.guests }} guest{{ s.guests === 1 ? '' : 's' }} · {{ s.rounds }} round{{ s.rounds === 1 ? '' : 's' }}</span>
              </div>
              <p class="mt-1 text-sm">Running total <strong>{{ formatCurrency(Number(s.total)) }}</strong> <span class="text-ink-subtle">(no tax)</span></p>
              <AppButton class="mt-3" :disabled="busy === s.session_id" @click="close(s)">Close tab &amp; clean table</AppButton>
            </li>
          </ul>
        </section>

        <section v-if="auth.isAdmin" class="mt-10">
          <div class="flex flex-wrap items-center justify-between gap-3">
            <h2 class="text-lg font-semibold">Table codes</h2>
            <AppButton @click="printTents">Print table tents</AppButton>
          </div>
          <p class="mt-1 text-sm text-ink-muted">Codes point to <code>{{ origin }}/t/…</code>. Open this page from the restaurant's own address so the codes use it.</p>
          <ul class="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <li v-for="t in tables" :key="t.table_id" class="rounded-xl border border-brand-100 bg-surface-elevated p-4 text-center">
              <img v-if="images[t.table_id]" :src="images[t.table_id]" :alt="`QR code for table ${t.table_number}`" class="mx-auto h-40 w-40">
              <p class="mt-2 font-semibold">Table {{ t.table_number }}<span v-if="t.zone" class="font-normal text-ink-muted"> · {{ t.zone }}</span></p>
              <button class="mt-2 text-sm font-medium text-brand-700 underline" :disabled="busy === t.table_id" @click="replace(t)">Replace code</button>
            </li>
          </ul>
        </section>
      </template>
    </div>

    <!-- what comes out of the printer: one tent card per table -->
    <div class="hidden print:block">
      <section v-for="t in tables" :key="t.table_id" class="tent">
        <img v-if="branding.logo.value" :src="branding.logo.value" :alt="printName" class="tent-logo">
        <h2 v-else class="tent-name">{{ printName }}</h2>
        <img v-if="images[t.table_id]" :src="images[t.table_id]" alt="" class="tent-qr">
        <p class="tent-cta">Scan to order from your table</p>
        <p class="tent-table">Table {{ t.table_number }}</p>
      </section>
    </div>
  </div>
</template>

<style scoped>
@media print {
  .tent { break-inside: avoid; page-break-after: always; text-align: center; padding: 24mm 10mm; }
  .tent-logo { max-height: 22mm; margin: 0 auto 8mm; }
  .tent-name { font-size: 26pt; margin-bottom: 8mm; }
  .tent-qr { width: 90mm; height: 90mm; margin: 0 auto; }
  .tent-cta { font-size: 16pt; margin-top: 8mm; }
  .tent-table { font-size: 34pt; font-weight: 700; margin-top: 4mm; }
}
</style>
