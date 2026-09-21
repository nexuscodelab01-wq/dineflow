<script setup lang="ts">
import { useDebounceFn } from '@vueuse/core'
import type { MenuItemDetail } from '~/types/menu'
import type { TableSessionView, WaiterTable } from '~/types/table'
import { fetchAdminMenu, updateOrderStatus, updateTableStatus } from '~/services/admin'
import { subscribeKitchen } from '~/services/realtime'
import { closeSession, fetchServiceRequests, fetchTabDetail, fetchWaiterFloor, finishServiceRequest, sendStaffRound, transferTab } from '~/services/table'
import type { ServiceRequest } from '~/types/table'
import { formatCurrency } from '~/utils/format'
import type { TableLine } from '~/utils/table-cart'
import { toRoundPayload } from '~/utils/table-cart'
import { attentionQueue, attentionReasons, planTables, transferTargets } from '~/utils/waiter'
import type { SseStatus } from '~/utils/sse'

definePageMeta({ layout: 'admin', middleware: ['staff'] })

const admin = useAdminStore()
const ui = useUiStore()
const enabled = useFeature('qr_table_ordering')

const tables = ref<WaiterTable[]>([])
const requests = ref<ServiceRequest[]>([])
const menu = ref<MenuItemDetail[]>([])
const loading = ref(true)
const error = ref('')
const connection = ref<SseStatus>('connecting')
const selectedId = ref<number | null>(null)
const tab = ref<TableSessionView | null>(null)
const busy = ref(false)

const plan = computed(() => planTables(tables.value))
const queue = computed(() => attentionQueue(tables.value))
const selected = computed(() => tables.value.find(t => t.table_id === selectedId.value) ?? null)
const reasons = computed(() => (selected.value ? attentionReasons(selected.value) : []))
const targets = computed(() => (selected.value ? transferTargets(tables.value, selected.value.table_id) : []))
const myRequests = computed(() => requests.value.filter(r => r.table_id === selectedId.value))

async function load() {
  await admin.initialize()
  const rid = admin.restaurantId
  if (!rid) return void (loading.value = false)
  try {
    ;[tables.value, requests.value] = await Promise.all([fetchWaiterFloor(rid), fetchServiceRequests(rid)])
    if (selected.value?.session) tab.value = await fetchTabDetail(rid, selected.value.session.session_id)
    else tab.value = null
    error.value = ''
  }
  catch (err) {
    if (loading.value) error.value = err instanceof Error ? err.message : 'Could not load the floor'
  }
  finally {
    loading.value = false
  }
}
const refreshSoon = useDebounceFn(load, 250)

let stream: { close: () => void } | null = null
let poll: ReturnType<typeof setInterval> | null = null
onMounted(async () => {
  await load()
  if (!admin.restaurantId) return
  stream = subscribeKitchen(admin.restaurantId, { onChange: refreshSoon, onStatus: (s) => { connection.value = s } })
  poll = setInterval(() => { if (document.visibilityState === 'visible') void load() }, 20000)
})
onBeforeUnmount(() => {
  stream?.close()
  if (poll) clearInterval(poll)
})

function pick(id: number) {
  selectedId.value = id
  void load()
}

async function act(action: () => Promise<unknown>, failure: string, success?: string) {
  if (busy.value) return
  busy.value = true
  try {
    await action()
    if (success) ui.success(success)
  }
  catch (err) {
    ui.error(err instanceof Error ? err.message : failure)
  }
  finally {
    await load()
    busy.value = false
  }
}

const answer = (r: ServiceRequest) => act(() => finishServiceRequest(admin.restaurantId!, r.id), 'Could not update the request')
const serve = (orderId: number) => act(() => updateOrderStatus(admin.restaurantId!, orderId, 'COMPLETED'), 'Could not mark it served', 'Marked as served')
const seat = (t: WaiterTable) => act(() => updateTableStatus(admin.restaurantId!, t.table_id, 'OCCUPIED'), 'Could not seat that table', `Table ${t.table_number} is occupied`)

async function closeTab() {
  const s = selected.value
  if (!s?.session) return
  const ok = await ui.confirm({
    title: `Close Table ${s.table_number}'s tab?`,
    message: 'Guests can no longer order, the table goes to cleaning and its QR code is replaced.',
    confirmLabel: 'Close tab',
    destructive: true,
  })
  if (ok) await act(() => closeSession(admin.restaurantId!, s.session!.session_id), 'Could not close the tab', `Table ${s.table_number} closed`)
}

// ---- moving a tab -------------------------------------------------------------------------------------

const moving = ref(false)
const moveTo = ref<number | null>(null)

async function confirmMove() {
  const s = selected.value
  if (!s?.session || moveTo.value == null) return
  const target = tables.value.find(t => t.table_id === moveTo.value)
  await act(async () => {
    await transferTab(admin.restaurantId!, s.session!.session_id, moveTo.value!)
    selectedId.value = moveTo.value
  }, 'Could not move the tab', `Moved to Table ${target?.table_number}`)
  moving.value = false
  moveTo.value = null
}

// ---- adding items for the table ------------------------------------------------------------------------

const adding = ref(false)
const sending = ref(false)
let sendKey: string | null = null

async function openPicker() {
  if (!menu.value.length && admin.restaurantId) {
    try {
      menu.value = await fetchAdminMenu(admin.restaurantId)
    }
    catch {
      return void ui.error('Could not load the menu')
    }
  }
  adding.value = true
}

async function sendRound(lines: TableLine[], notes: string) {
  const s = selected.value
  if (!s?.session || sending.value) return
  sending.value = true
  sendKey ??= crypto.randomUUID()
  try {
    await sendStaffRound(admin.restaurantId!, s.session.session_id, toRoundPayload(lines, notes), sendKey)
    sendKey = null
    adding.value = false
    ui.success('Sent to the kitchen')
    await load()
  }
  catch (err) {
    sendKey = null
    ui.error(err instanceof Error ? err.message : 'Could not send')
  }
  finally {
    sending.value = false
  }
}

const statusLabel = (s: string) => ({ CONFIRMED: 'Received', PREPARING: 'Being prepared', READY: 'Ready to serve', COMPLETED: 'Served', CANCELLED: 'Cancelled', PENDING: 'Sending…' } as Record<string, string>)[s] ?? s
</script>

<template>
  <div>
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="font-display text-3xl font-semibold text-brand-900">Waiter view</h1>
        <p class="text-sm text-ink-muted">Every table, its tab, and who needs you.</p>
      </div>
      <span
        class="inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-semibold"
        :class="connection === 'live' ? 'bg-emerald-100 text-emerald-900' : 'bg-amber-100 text-amber-900'"
        role="status"
      >
        <span class="h-2 w-2 rounded-full" :class="connection === 'live' ? 'bg-emerald-500' : 'animate-pulse bg-amber-500'" />
        {{ connection === 'live' ? 'Live' : 'Reconnecting…' }}
      </span>
    </div>

    <p v-if="!enabled" class="mt-6 rounded-xl bg-amber-50 p-4 text-amber-900">Table ordering isn't switched on for this restaurant.</p>
    <div v-else-if="loading" class="mt-6 h-64 animate-pulse rounded-2xl bg-brand-100/60" />
    <p v-else-if="error" class="mt-6 rounded-xl bg-red-50 p-4 text-red-700">{{ error }}</p>

    <div v-else class="mt-4 grid gap-6 lg:grid-cols-[1fr_22rem]">
      <div>
        <section v-if="queue.length" class="mb-4" aria-live="polite">
          <h2 class="mb-2 text-sm font-semibold uppercase tracking-wide text-amber-800">Needs you now</h2>
          <ul class="flex flex-wrap gap-2">
            <li v-for="t in queue" :key="t.table_id">
              <button class="rounded-xl border border-amber-400 bg-amber-100 px-3 py-2 text-left text-sm" @click="pick(t.table_id)">
                <strong>Table {{ t.table_number }}</strong>
                <span class="block text-xs text-amber-900">{{ attentionReasons(t).join(' · ') }}</span>
              </button>
            </li>
          </ul>
        </section>

        <FloorPlan :tables="plan" :selected-id="selectedId" @select="pick" />
        <p class="mt-2 text-xs text-ink-subtle">Tap a table. The amount on a table is its tab so far, with tax.</p>
      </div>

      <aside class="rounded-2xl border border-brand-100 bg-surface-elevated p-4" data-testid="table-panel">
        <p v-if="!selected" class="py-10 text-center text-ink-muted">Pick a table to see its tab.</p>

        <template v-else>
          <div class="flex items-start justify-between">
            <div>
              <h2 class="font-display text-2xl font-semibold text-brand-900">Table {{ selected.table_number }}</h2>
              <p class="text-xs text-ink-subtle">Seats {{ selected.capacity }}<span v-if="selected.zone"> · {{ selected.zone }}</span></p>
            </div>
            <StatusBadge :status="selected.status" />
          </div>

          <!-- no tab yet -->
          <div v-if="!selected.session" class="mt-4 space-y-3">
            <p class="text-sm text-ink-muted">
              {{ selected.status === 'OCCUPIED' ? 'Seated, but nobody has started a tab yet.' : selected.status === 'CLEANING' ? 'Being cleaned.' : selected.status === 'RESERVED' ? 'Reserved.' : 'Free.' }}
            </p>
            <AppButton v-if="selected.status !== 'OCCUPIED'" class="w-full" :disabled="busy" @click="seat(selected)">Seat guests here</AppButton>
            <p v-else class="text-xs text-ink-subtle">Guests can now scan the table's QR code to order, or you can start their order below once they have a tab.</p>
          </div>

          <!-- a live tab -->
          <template v-else>
            <ul v-if="reasons.length" class="mt-3 space-y-1">
              <li v-for="r in reasons" :key="r" class="rounded-md bg-amber-100 px-2 py-1 text-sm font-semibold text-amber-950">{{ r }}</li>
            </ul>
            <div v-for="r in myRequests" :key="r.id" class="mt-2 flex items-center justify-between gap-2 text-sm">
              <span>{{ r.kind === 'BILL' ? 'Bill requested' : 'Waiter requested' }}<span v-if="r.asked_by" class="text-ink-muted"> · {{ r.asked_by }}</span></span>
              <AppButton :disabled="busy" @click="answer(r)">Done</AppButton>
            </div>

            <p class="mt-4 text-sm text-ink-muted">{{ tab?.guests.length ? tab.guests.join(', ') : `${selected.session.guests} guest${selected.session.guests === 1 ? '' : 's'}` }}</p>
            <ul class="mt-2 space-y-3">
              <li v-for="round in tab?.rounds ?? []" :key="round.order_id" class="rounded-xl border border-brand-100 p-3">
                <div class="flex items-center justify-between gap-2">
                  <p class="font-semibold">Round {{ round.round_no }}<span v-if="round.ordered_by" class="font-normal text-ink-muted"> · {{ round.ordered_by }}</span></p>
                  <StatusBadge :status="round.status" />
                </div>
                <p class="text-xs text-ink-subtle">{{ statusLabel(round.status) }}</p>
                <ul class="mt-1 text-sm">
                  <li v-for="(line, i) in round.items" :key="i"><strong>{{ line.quantity }}×</strong> {{ line.name }}<span v-if="line.options.length" class="text-ink-muted"> ({{ line.options.join(', ') }})</span></li>
                </ul>
                <AppButton v-if="round.status === 'READY'" class="mt-2 w-full" :disabled="busy" @click="serve(round.order_id)">Mark served</AppButton>
              </li>
              <li v-if="!(tab?.rounds.length)" class="text-sm text-ink-subtle">Nothing ordered yet.</li>
            </ul>
            <p class="mt-3 flex justify-between border-t border-brand-100 pt-3 font-semibold"><span>Tab (with tax)</span><span>{{ formatCurrency(Number(selected.session.total)) }}</span></p>

            <div class="mt-4 grid gap-2">
              <AppButton :disabled="busy" @click="openPicker">Add items for the table</AppButton>
              <button class="rounded-lg border border-brand-200 px-4 py-2 text-sm font-semibold text-brand-800 hover:bg-brand-50" :disabled="busy || !targets.length" @click="moving = true">Move to another table</button>
              <button class="rounded-lg border border-red-300 px-4 py-2 text-sm font-semibold text-red-700 hover:bg-red-50" :disabled="busy" @click="closeTab">Close tab &amp; clean table</button>
            </div>
          </template>
        </template>
      </aside>
    </div>

    <StaffRoundPicker v-if="adding && selected" :items="menu" :table-number="selected.table_number" :sending="sending" @send="sendRound" @close="adding = false" />

    <div v-if="moving && selected" class="fixed inset-0 z-40 flex items-center justify-center bg-black/40 p-4" role="dialog" aria-modal="true" aria-label="Move tab" @click.self="moving = false">
      <div class="w-full max-w-sm rounded-2xl bg-white p-5">
        <h2 class="font-display text-xl font-semibold text-brand-900">Move Table {{ selected.table_number }}'s tab</h2>
        <p class="mt-1 text-sm text-ink-muted">The kitchen will see the new table. The old one goes to cleaning and its QR code is replaced.</p>
        <label class="mt-4 block text-sm font-medium">Move to
          <select v-model="moveTo" class="mt-1 w-full rounded-lg border border-brand-200 px-3 py-2.5 text-base">
            <option :value="null" disabled>Choose a free table…</option>
            <option v-for="t in targets" :key="t.table_id" :value="t.table_id">Table {{ t.table_number }} (seats {{ t.capacity }}{{ t.zone ? `, ${t.zone}` : '' }})</option>
          </select>
        </label>
        <div class="mt-4 flex gap-2">
          <AppButton class="flex-1" :disabled="moveTo == null || busy" @click="confirmMove">Move tab</AppButton>
          <button class="rounded-lg border px-4 py-2 text-sm" @click="moving = false">Cancel</button>
        </div>
      </div>
    </div>
  </div>
</template>
