<script setup lang="ts">
import type { Category, MenuItem, MenuItemDetail } from '~/types/menu'
import type { TableInfo, TableSessionView } from '~/types/table'
import { fetchCategories, fetchMenu, fetchMenuItem } from '~/services/menu'
import { subscribeTableSession } from '~/services/realtime'
import { askForService, fetchTableInfo, fetchTableSession, joinTable, sendRound } from '~/services/table'
import { ApiError } from '~/utils/api-error'
import { formatCurrency } from '~/utils/format'
import { resolveMediaUrl } from '~/utils/media'
import { addLine, changeQuantity, lineCount, subtotal, toRoundPayload, type TableLine } from '~/utils/table-cart'
import { clearPass, loadPass, savePass, type TablePass } from '~/utils/table-pass'

definePageMeta({ layout: 'table' })

const route = useRoute()
const restaurant = useRestaurantStore()
const ui = useUiStore()
const tableToken = computed(() => String(route.params.token))

type Phase = 'loading' | 'invalid' | 'unavailable' | 'closed' | 'join' | 'ordering' | 'ended'
const phase = ref<Phase>('loading')
const info = ref<TableInfo | null>(null)
const pass = ref<TablePass | null>(null)
const guestName = ref('')
const joining = ref(false)
const problem = ref('')

// ---- getting in --------------------------------------------------------------------------------------

async function start() {
  problem.value = ''
  const current = await restaurant.load()
  if (!current) return void (phase.value = 'invalid')
  try {
    info.value = await fetchTableInfo(tableToken.value, current.id)
  }
  catch (err) {
    // The code on the table was replaced (the tab moved to another table, say) but this phone still holds a valid
    // pass for the open tab: carry on ordering instead of showing "invalid".
    const saved = err instanceof ApiError && err.status === 404 ? loadPass(localStorage, tableToken.value, current.id) : null
    if (saved) {
      pass.value = saved
      try {
        await refreshSession()
        info.value = { restaurant_id: current.id, restaurant_name: current.name, table_number: session.value!.table_number, ordering_open: true }
        phase.value = 'ordering'
        return void beginOrdering()
      }
      catch {
        clearPass(localStorage)
        pass.value = null
        if (phase.value === 'ended') return // the tab really is over: say so, not "invalid"
      }
    }
    phase.value = err instanceof ApiError && err.status === 403 ? 'unavailable' : 'invalid'
    if (phase.value === 'invalid' && !(err instanceof ApiError && err.status === 404)) problem.value = 'We could not reach the restaurant. Check your connection and try again.'
    return
  }
  pass.value = loadPass(localStorage, tableToken.value, current.id)
  if (pass.value) {
    try {
      await refreshSession()
      phase.value = 'ordering'
      return void beginOrdering()
    }
    catch {
      // an old pass for a finished session: fall through and start again
      clearPass(localStorage)
      pass.value = null
    }
  }
  phase.value = info.value.ordering_open ? 'join' : 'closed'
}

async function join() {
  if (!info.value || joining.value) return
  joining.value = true
  problem.value = ''
  try {
    const res = await joinTable(tableToken.value, info.value.restaurant_id, guestName.value.trim() || null)
    pass.value = { token: res.access_token, sessionId: res.session_id, tableToken: tableToken.value, restaurantId: info.value.restaurant_id }
    savePass(localStorage, pass.value)
    await refreshSession()
    phase.value = 'ordering'
    beginOrdering()
  }
  catch (err) {
    problem.value = err instanceof Error ? err.message : 'Could not start your table'
    if (err instanceof ApiError && err.status === 403) await start()
  }
  finally {
    joining.value = false
  }
}

// ---- the shared tab ----------------------------------------------------------------------------------

const session = ref<TableSessionView | null>(null)
let poller: ReturnType<typeof setInterval> | null = null
let live: { close: () => void } | null = null

async function refreshSession() {
  if (!pass.value) return
  try {
    session.value = await fetchTableSession(pass.value.token)
  }
  catch (err) {
    if (err instanceof ApiError && err.status === 401) endSession()
    throw err
  }
}

function endSession() {
  clearPass(localStorage)
  pass.value = null
  session.value = null
  stopPolling()
  phase.value = 'ended'
}

function stopPolling() {
  if (poller) clearInterval(poller)
  poller = null
  live?.close()
  live = null
}

// The kitchen changes statuses and other guests add rounds: those arrive instantly over a live connection.
// The slow refresh only covers a connection that has dropped, and only runs while the page is visible.
function beginOrdering() {
  stopPolling()
  void loadMenu()
  if (pass.value) {
    live = subscribeTableSession(pass.value.token, {
      onChange: () => void refreshSession().catch(() => {}),
      // The server refuses a pass whose tab has ended; asking for the tab makes that known to the page.
      onStatus: (status) => { if (status === 'closed') void refreshSession().catch(() => {}) },
    })
  }
  poller = setInterval(() => {
    if (document.visibilityState === 'visible') refreshSession().catch(() => {})
  }, 30000)
}

onMounted(start)
onUnmounted(stopPolling)

// ---- the menu ----------------------------------------------------------------------------------------

const categories = ref<Category[]>([])
const items = ref<MenuItem[]>([])
const activeCategory = ref<number | null>(null)
const menuError = ref('')

async function loadMenu() {
  if (!info.value) return
  try {
    const [cats, menu] = await Promise.all([
      fetchCategories(info.value.restaurant_id),
      fetchMenu(info.value.restaurant_id, { page_size: 100, sort: 'popular' }),
    ])
    categories.value = cats
    items.value = menu.items
  }
  catch {
    menuError.value = 'We could not load the menu. Pull down to try again.'
  }
}

const visibleItems = computed(() => items.value.filter(i => activeCategory.value == null || i.category_id === activeCategory.value))

// ---- picking an item ---------------------------------------------------------------------------------

const picking = ref<MenuItemDetail | null>(null)
const pickLoading = ref(false)
const pickQty = ref(1)
const pickNote = ref('')
const pickOptions = ref<Record<number, number[]>>({})
const pickError = ref('')

async function pick(item: MenuItem) {
  if (!item.is_available || !info.value) return
  pickLoading.value = true
  pickError.value = ''
  try {
    const detail = await fetchMenuItem(item.id, info.value.restaurant_id)
    pickQty.value = 1
    pickNote.value = ''
    pickOptions.value = {}
    for (const m of detail.modifiers) {
      const defaults = m.options.filter(o => o.is_default).map(o => o.id)
      pickOptions.value[m.id] = m.max_selections === 1 ? [defaults[0] ?? (m.is_required ? m.options[0]?.id : undefined)].filter(Boolean) as number[] : defaults
    }
    picking.value = detail
  }
  catch {
    ui.error('Could not open that dish. Please try again.')
  }
  finally {
    pickLoading.value = false
  }
}

function toggleOption(modifierId: number, optionId: number, max: number) {
  const current = pickOptions.value[modifierId] ?? []
  if (max === 1) pickOptions.value[modifierId] = [optionId]
  else if (current.includes(optionId)) pickOptions.value[modifierId] = current.filter(id => id !== optionId)
  else if (current.length < max) pickOptions.value[modifierId] = [...current, optionId]
}

const pickUnitPrice = computed(() => {
  const item = picking.value
  if (!item) return 0
  let total = Number(item.price)
  for (const m of item.modifiers) for (const o of m.options) if ((pickOptions.value[m.id] ?? []).includes(o.id)) total += Number(o.price_adjustment)
  return total
})

const lines = ref<TableLine[]>([])

function addPicked() {
  const item = picking.value
  if (!item) return
  for (const m of item.modifiers) {
    if (m.is_required && (pickOptions.value[m.id] ?? []).length < Math.max(m.min_selections, 1)) {
      pickError.value = `Please choose ${m.name}`
      return
    }
  }
  const optionIds = Object.values(pickOptions.value).flat()
  const optionNames = item.modifiers.flatMap(m => m.options.filter(o => optionIds.includes(o.id)).map(o => o.name))
  lines.value = addLine(lines.value, {
    menuItemId: item.id, name: item.name, unitPrice: pickUnitPrice.value, quantity: pickQty.value, optionIds, optionNames,
    instructions: pickNote.value || undefined,
  })
  picking.value = null
}

// ---- sending -----------------------------------------------------------------------------------------

const reviewing = ref(false)
const roundNotes = ref('')
const sending = ref(false)
const tab = ref<'menu' | 'table'>('menu')
let sendKey: string | null = null // stays the same across retries of one send, so a double tap can't order twice

async function send() {
  if (!pass.value || sending.value || !lines.value.length) return
  sending.value = true
  sendKey ??= crypto.randomUUID()
  try {
    await sendRound(pass.value.token, toRoundPayload(lines.value, roundNotes.value), sendKey)
    sendKey = null
    lines.value = []
    roundNotes.value = ''
    reviewing.value = false
    tab.value = 'table'
    ui.success('Sent to the kitchen')
    await refreshSession().catch(() => {})
  }
  catch (err) {
    if (err instanceof ApiError && err.status === 401) return endSession()
    if (err instanceof ApiError && err.status === 400) sendKey = null // the round was refused: a corrected one is a new send
    ui.error(err instanceof Error ? err.message : 'Could not send. Please try again.')
  }
  finally {
    sending.value = false
  }
}

const asking = ref<string | null>(null)
const waiting = (kind: string) => session.value?.requests.includes(kind) ?? false

async function ask(kind: 'WAITER' | 'BILL') {
  if (!pass.value || asking.value || waiting(kind)) return
  asking.value = kind
  try {
    await askForService(pass.value.token, kind)
    await refreshSession().catch(() => {})
    ui.success(kind === 'WAITER' ? 'A member of staff is on their way' : 'We will bring your bill shortly')
  }
  catch (err) {
    if (err instanceof ApiError && err.status === 401) return endSession()
    ui.error(err instanceof Error ? err.message : 'Could not send that. Please try again.')
  }
  finally {
    asking.value = null
  }
}

const statusText: Record<string, string> = {
  PENDING: 'Sending…', CONFIRMED: 'Received', PREPARING: 'Being prepared', READY: 'Ready', COMPLETED: 'Served', DELIVERED: 'Served', CANCELLED: 'Cancelled',
}
</script>

<template>
  <main class="mx-auto w-full max-w-2xl flex-1 px-4 pb-32 pt-6">
    <p v-if="phase === 'loading'" class="py-20 text-center text-ink-muted">Opening your table…</p>

    <section v-else-if="phase === 'invalid'" class="py-16 text-center">
      <h1 class="font-display text-2xl font-semibold text-brand-900">This QR code isn't valid</h1>
      <p class="mt-2 text-ink-muted">{{ problem || 'It may have been replaced. Please ask a member of staff.' }}</p>
    </section>

    <section v-else-if="phase === 'unavailable'" class="py-16 text-center">
      <h1 class="font-display text-2xl font-semibold text-brand-900">Ordering from the table isn't available here</h1>
      <p class="mt-2 text-ink-muted">Please ask a member of staff to take your order.</p>
    </section>

    <section v-else-if="phase === 'closed' && info" class="py-16 text-center">
      <p class="text-sm font-semibold uppercase tracking-wide text-brand-700">Table {{ info.table_number }}</p>
      <h1 class="font-display mt-2 text-2xl font-semibold text-brand-900">Not open for ordering yet</h1>
      <p class="mx-auto mt-2 max-w-sm text-ink-muted">{{ info.reason }}</p>
      <AppButton class="mt-6" @click="start">Check again</AppButton>
    </section>

    <section v-else-if="phase === 'ended'" class="py-16 text-center">
      <h1 class="font-display text-2xl font-semibold text-brand-900">This table's tab has ended</h1>
      <p class="mt-2 text-ink-muted">Thank you for dining with us! To order again, ask a member of staff and scan the code once more.</p>
    </section>

    <section v-else-if="phase === 'join' && info" class="py-10">
      <p class="text-sm font-semibold uppercase tracking-wide text-brand-700">Table {{ info.table_number }}</p>
      <h1 class="font-display mt-1 text-3xl font-semibold text-brand-900">Welcome to {{ info.restaurant_name }}</h1>
      <p class="mt-2 text-ink-muted">Order from your phone. Everyone at the table shares one tab, and orders go straight to the kitchen.</p>
      <form class="mt-6 space-y-4" @submit.prevent="join">
        <div>
          <label for="guest-name" class="mb-1 block text-sm font-medium">Your name <span class="text-ink-subtle">(optional)</span></label>
          <input id="guest-name" v-model="guestName" type="text" maxlength="80" autocomplete="given-name" class="w-full rounded-lg border border-brand-200 px-3 py-3 text-base" placeholder="So your table knows who ordered what">
        </div>
        <p v-if="problem" class="text-sm text-red-600">{{ problem }}</p>
        <AppButton type="submit" class="w-full py-3 text-base" :disabled="joining">{{ joining ? 'Starting…' : 'Start ordering' }}</AppButton>
      </form>
    </section>

    <template v-else-if="phase === 'ordering' && info">
      <div class="flex items-baseline justify-between">
        <h1 class="font-display text-2xl font-semibold text-brand-900">Table {{ info.table_number }}</h1>
        <span v-if="session?.guests.length" class="text-sm text-ink-muted">{{ session.guests.join(', ') }}</span>
      </div>

      <div class="mt-4 grid grid-cols-2 rounded-xl bg-brand-50 p-1 text-sm font-semibold" role="tablist">
        <button role="tab" :aria-selected="tab === 'menu'" class="rounded-lg py-2" :class="tab === 'menu' ? 'bg-white text-brand-900 shadow-sm' : 'text-ink-muted'" @click="tab = 'menu'">Menu</button>
        <button role="tab" :aria-selected="tab === 'table'" class="rounded-lg py-2" :class="tab === 'table' ? 'bg-white text-brand-900 shadow-sm' : 'text-ink-muted'" @click="tab = 'table'">
          Our table<span v-if="session?.rounds.length"> ({{ session.rounds.length }})</span>
        </button>
      </div>

      <!-- MENU -->
      <div v-show="tab === 'menu'" class="mt-4">
        <div class="-mx-4 flex gap-2 overflow-x-auto px-4 pb-2">
          <button class="whitespace-nowrap rounded-full px-3 py-1.5 text-sm font-medium" :class="activeCategory == null ? 'bg-brand-700 text-white' : 'bg-brand-100 text-brand-900'" @click="activeCategory = null">All</button>
          <button v-for="c in categories" :key="c.id" class="whitespace-nowrap rounded-full px-3 py-1.5 text-sm font-medium" :class="activeCategory === c.id ? 'bg-brand-700 text-white' : 'bg-brand-100 text-brand-900'" @click="activeCategory = c.id">{{ c.name }}</button>
        </div>
        <p v-if="menuError" class="mt-4 text-sm text-red-600">{{ menuError }}</p>
        <ul class="mt-2 divide-y divide-brand-100">
          <li v-for="item in visibleItems" :key="item.id">
            <button class="flex w-full items-center gap-3 py-3 text-left disabled:opacity-50" :disabled="!item.is_available || pickLoading" @click="pick(item)">
              <span class="min-w-0 flex-1">
                <span class="block font-semibold text-ink">{{ item.name }}</span>
                <span v-if="item.description" class="line-clamp-2 block text-sm text-ink-muted">{{ item.description }}</span>
                <span class="mt-1 block text-sm font-semibold text-brand-800">{{ item.is_available ? formatCurrency(Number(item.price)) : 'Sold out' }}</span>
              </span>
              <img v-if="item.image_url" :src="resolveMediaUrl(item.image_url) ?? ''" :alt="item.name" class="h-16 w-16 rounded-lg object-cover">
              <span v-if="item.is_available" class="flex h-9 w-9 items-center justify-center rounded-full bg-brand-700 text-xl text-white" aria-hidden="true">+</span>
            </button>
          </li>
        </ul>
      </div>

      <!-- OUR TABLE -->
      <div v-show="tab === 'table'" class="mt-4 space-y-3">
        <p v-if="!session?.rounds.length" class="py-10 text-center text-ink-muted">Nothing sent yet. Pick something from the menu.</p>
        <article v-for="round in session?.rounds ?? []" :key="round.order_id" class="rounded-xl border border-brand-100 bg-surface-elevated p-4">
          <div class="flex items-center justify-between">
            <h2 class="font-semibold">Round {{ round.round_no }}<span v-if="round.ordered_by" class="font-normal text-ink-muted"> · {{ round.ordered_by }}</span></h2>
            <StatusBadge :status="round.status" />
          </div>
          <p class="text-xs text-ink-subtle">{{ statusText[round.status] ?? round.status }}</p>
          <ul class="mt-2 space-y-1 text-sm">
            <li v-for="(line, i) in round.items" :key="i">
              <span class="font-semibold">{{ line.quantity }}×</span> {{ line.name }}
              <span v-if="line.options.length" class="text-ink-muted"> ({{ line.options.join(', ') }})</span>
              <span v-if="line.special_instructions" class="block text-ink-muted">Note: {{ line.special_instructions }}</span>
            </li>
          </ul>
        </article>
        <div v-if="session?.rounds.length" class="flex items-center justify-between rounded-xl bg-brand-50 p-4 font-semibold">
          <span>Table total (with tax)</span><span>{{ formatCurrency(Number(session.total)) }}</span>
        </div>
        <div class="grid grid-cols-2 gap-3 pt-2">
          <button class="rounded-xl border border-brand-200 bg-white px-3 py-3 text-sm font-semibold text-brand-900 disabled:opacity-60" :disabled="asking === 'WAITER' || waiting('WAITER')" @click="ask('WAITER')">
            {{ waiting('WAITER') ? 'Waiter is on the way ✓' : 'Call a waiter' }}
          </button>
          <button class="rounded-xl bg-brand-700 px-3 py-3 text-sm font-semibold text-white disabled:opacity-60" :disabled="!session?.rounds.length || asking === 'BILL' || waiting('BILL')" @click="ask('BILL')">
            {{ waiting('BILL') ? 'Bill requested ✓' : 'Ask for the bill' }}
          </button>
        </div>
        <p v-if="session?.rounds.length" class="text-center text-sm text-ink-muted">You pay at the table when you are ready.</p>
      </div>

      <!-- cart bar -->
      <div v-if="lines.length && tab === 'menu'" class="fixed inset-x-0 bottom-0 border-t border-brand-100 bg-surface-elevated p-3 shadow-lg">
        <div class="mx-auto max-w-2xl">
          <AppButton class="w-full py-3 text-base" @click="reviewing = true">Review order · {{ lineCount(lines) }} item{{ lineCount(lines) === 1 ? '' : 's' }} · {{ formatCurrency(subtotal(lines)) }}</AppButton>
        </div>
      </div>
    </template>

    <!-- dish sheet -->
    <div v-if="picking" class="fixed inset-0 z-40 flex items-end bg-black/40" role="dialog" aria-modal="true" :aria-label="picking.name" @click.self="picking = null">
      <div class="max-h-[90vh] w-full overflow-y-auto rounded-t-2xl bg-surface-elevated p-5">
        <div class="flex items-start justify-between gap-3">
          <h2 class="font-display text-2xl font-semibold text-brand-900">{{ picking.name }}</h2>
          <button class="text-2xl leading-none text-ink-muted" aria-label="Close" @click="picking = null">×</button>
        </div>
        <p v-if="picking.description" class="mt-1 text-ink-muted">{{ picking.description }}</p>
        <div v-for="m in picking.modifiers" :key="m.id" class="mt-4">
          <p class="font-semibold">{{ m.name }} <span class="text-xs font-normal text-ink-subtle">{{ m.is_required ? 'Required' : 'Optional' }}</span></p>
          <label v-for="o in m.options" :key="o.id" class="mt-2 flex items-center justify-between rounded-lg border border-brand-100 px-3 py-2.5">
            <span class="flex items-center gap-2 text-sm">
              <input :type="m.max_selections === 1 ? 'radio' : 'checkbox'" :name="`m-${m.id}`" :checked="(pickOptions[m.id] ?? []).includes(o.id)" @change="toggleOption(m.id, o.id, m.max_selections)">
              {{ o.name }}
            </span>
            <span v-if="Number(o.price_adjustment) > 0" class="text-sm text-ink-muted">+{{ formatCurrency(Number(o.price_adjustment)) }}</span>
          </label>
        </div>
        <label class="mt-4 block text-sm font-medium">Special requests
          <input v-model="pickNote" type="text" maxlength="200" class="mt-1 w-full rounded-lg border border-brand-200 px-3 py-2.5 text-base" placeholder="No onions, allergy…">
        </label>
        <div class="mt-4 flex items-center justify-between">
          <div class="flex items-center gap-3">
            <button class="h-9 w-9 rounded-full border border-brand-200 text-lg" aria-label="Fewer" @click="pickQty = Math.max(1, pickQty - 1)">−</button>
            <span class="w-6 text-center font-semibold">{{ pickQty }}</span>
            <button class="h-9 w-9 rounded-full border border-brand-200 text-lg" aria-label="More" @click="pickQty = Math.min(20, pickQty + 1)">+</button>
          </div>
        </div>
        <p v-if="pickError" class="mt-3 text-sm text-red-600">{{ pickError }}</p>
        <AppButton class="mt-4 w-full py-3 text-base" @click="addPicked">Add · {{ formatCurrency(pickUnitPrice * pickQty) }}</AppButton>
      </div>
    </div>

    <!-- review sheet -->
    <div v-if="reviewing" class="fixed inset-0 z-40 flex items-end bg-black/40" role="dialog" aria-modal="true" aria-label="Review your order" @click.self="reviewing = false">
      <div class="max-h-[90vh] w-full overflow-y-auto rounded-t-2xl bg-surface-elevated p-5">
        <div class="flex items-start justify-between">
          <h2 class="font-display text-2xl font-semibold text-brand-900">Your order</h2>
          <button class="text-2xl leading-none text-ink-muted" aria-label="Close" @click="reviewing = false">×</button>
        </div>
        <ul class="mt-3 divide-y divide-brand-100">
          <li v-for="l in lines" :key="l.key" class="flex items-center justify-between gap-3 py-3">
            <span class="min-w-0 text-sm">
              <span class="block font-semibold">{{ l.name }}</span>
              <span v-if="l.optionNames.length" class="block text-ink-muted">{{ l.optionNames.join(', ') }}</span>
              <span v-if="l.instructions" class="block text-ink-muted">Note: {{ l.instructions }}</span>
            </span>
            <span class="flex shrink-0 items-center gap-2">
              <button class="h-8 w-8 rounded-full border border-brand-200" aria-label="Fewer" @click="lines = changeQuantity(lines, l.key, -1)">−</button>
              <span class="w-5 text-center text-sm font-semibold">{{ l.quantity }}</span>
              <button class="h-8 w-8 rounded-full border border-brand-200" aria-label="More" @click="lines = changeQuantity(lines, l.key, 1)">+</button>
            </span>
          </li>
        </ul>
        <label class="mt-2 block text-sm font-medium">Anything for the kitchen?
          <input v-model="roundNotes" type="text" maxlength="200" class="mt-1 w-full rounded-lg border border-brand-200 px-3 py-2.5 text-base" placeholder="Bring starters first…">
        </label>
        <p class="mt-3 flex justify-between text-sm"><span>Subtotal</span><span class="font-semibold">{{ formatCurrency(subtotal(lines)) }}</span></p>
        <p class="text-xs text-ink-subtle">Tax is added to your table's bill. You pay at the end of the meal.</p>
        <AppButton class="mt-4 w-full py-3 text-base" :disabled="sending || !lines.length" @click="send">{{ sending ? 'Sending…' : 'Send to kitchen' }}</AppButton>
      </div>
    </div>
  </main>
</template>
