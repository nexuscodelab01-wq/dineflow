<script setup lang="ts">
import { useDebounceFn } from '@vueuse/core'
import type { KitchenBoard } from '~/types/admin'
import type { MenuItemDetail } from '~/types/menu'
import type { Order } from '~/types/order'
import { bumpItem, bumpTicket, fetchAdminMenu, fetchKitchenBoard, recallItem, setSoldOut, updateOrderStatus } from '~/services/admin'
import { subscribeKitchen } from '~/services/realtime'
import { playDing, unlockSound } from '~/utils/beep'
import { allDayCounts, newOrderIds, STATIONS, ticketsFor } from '~/utils/kitchen'
import type { SseStatus } from '~/utils/sse'

definePageMeta({ layout: 'admin', middleware: ['staff'] })

const admin = useAdminStore()
const ui = useUiStore()
const board = ref<KitchenBoard | null>(null)
const soldOut = ref<MenuItemDetail[]>([])
const loading = ref(true)
const busy = ref(false)
const connection = ref<SseStatus>('connecting')

// ---- this screen's own settings (a tablet at the bar stays on "Bar"), kept in the browser -------------

const station = ref<string | null>(null)
const soundOn = ref(false)
const KEY_STATION = 'dineflow_kitchen_station'
const KEY_SOUND = 'dineflow_kitchen_sound'

function remember(key: string, value: string | null) {
  try {
    if (value === null) localStorage.removeItem(key)
    else localStorage.setItem(key, value)
  }
  catch { /* private mode: the setting just lasts until the page closes */ }
}

watch(station, v => remember(KEY_STATION, v))
watch(soundOn, v => remember(KEY_SOUND, v ? '1' : null))

function toggleSound() {
  soundOn.value = !soundOn.value
  if (soundOn.value) {
    unlockSound() // this click is the tap browsers require before any sound may play
    playDing()
  }
}

// ---- data --------------------------------------------------------------------------------------------

const tickets = computed(() => ticketsFor(board.value, station.value))
const todo = computed(() => tickets.value.filter(t => t.state === 'todo'))
const finished = computed(() => tickets.value.filter(t => t.state === 'done'))
const counts = computed(() => allDayCounts(todo.value))

let seen: Set<number> | null = null // the first load is not "new"

async function load() {
  await admin.initialize()
  if (!admin.restaurantId) return
  try {
    const [next, menu] = await Promise.all([fetchKitchenBoard(admin.restaurantId), fetchAdminMenu(admin.restaurantId)])
    board.value = next
    soldOut.value = menu.filter(m => !m.is_available)
    const fresh = newOrderIds(seen, tickets.value)
    seen = new Set(tickets.value.map(t => t.order.id))
    if (fresh.length && soundOn.value) playDing()
  }
  catch (err) {
    if (loading.value) ui.error(err instanceof Error ? err.message : 'Could not load orders')
  }
  finally {
    loading.value = false
  }
}

// Several events can arrive together (an order plus its status change): refetch once.
const refreshSoon = useDebounceFn(load, 250)

// ---- a clock for the timers --------------------------------------------------------------------------

const now = ref(Date.now())
let clock: ReturnType<typeof setInterval> | null = null
let poll: ReturnType<typeof setInterval> | null = null
let stream: { close: () => void } | null = null

onMounted(async () => {
  try {
    const saved = localStorage.getItem(KEY_STATION)
    if (saved && STATIONS.some(s => s.key === saved)) station.value = saved
    soundOn.value = localStorage.getItem(KEY_SOUND) === '1'
  }
  catch { /* defaults */ }
  // A reloaded tablet has not been tapped yet, so sound stays locked until the first touch anywhere.
  window.addEventListener('pointerdown', unlockSound, { once: true })
  clock = setInterval(() => { now.value = Date.now() }, 1000)
  await load()
  if (!admin.restaurantId) return
  stream = subscribeKitchen(admin.restaurantId, { onChange: refreshSoon, onStatus: (s) => { connection.value = s } })
  // Safety net: rarely while the live stream is healthy, often when it is not.
  poll = setInterval(load, 15000)
  document.addEventListener('visibilitychange', onVisible)
})

onBeforeUnmount(() => {
  if (clock) clearInterval(clock)
  if (poll) clearInterval(poll)
  stream?.close()
  document.removeEventListener('visibilitychange', onVisible)
  window.removeEventListener('pointerdown', unlockSound)
})

// A tablet that slept or a background tab may have missed events: catch up when it wakes.
function onVisible() {
  if (document.visibilityState === 'visible') void load()
}

// ---- actions -----------------------------------------------------------------------------------------

async function run(action: () => Promise<unknown>, failure: string) {
  if (!admin.restaurantId || busy.value) return
  busy.value = true
  try {
    await action()
  }
  catch (err) {
    ui.error(err instanceof Error ? err.message : failure)
  }
  finally {
    await load()
    busy.value = false
  }
}

const bump = (id: number) => run(() => bumpItem(admin.restaurantId!, id), 'Could not bump that dish')
const recall = (id: number) => run(() => recallItem(admin.restaurantId!, id), 'Could not recall that dish')
const bumpAll = (order: Order) => run(() => bumpTicket(admin.restaurantId!, order.id, station.value), 'Could not bump that ticket')
const complete = (order: Order) => run(() => updateOrderStatus(admin.restaurantId!, order.id, 'COMPLETED'), 'Could not clear that order')

function eightySix(menuItemId: number, name: string) {
  if (!window.confirm(`86 "${name}"? It disappears from every menu and QR ordering right away.`)) return
  void run(async () => {
    await setSoldOut(admin.restaurantId!, menuItemId, true)
    ui.success(`${name} is off the menu`)
  }, 'Could not take that dish off')
}

function bringBack(item: MenuItemDetail) {
  void run(async () => {
    await setSoldOut(admin.restaurantId!, item.id, false)
    ui.success(`${item.name} is back on the menu`)
  }, 'Could not put that dish back')
}

function fullscreen() {
  if (document.fullscreenElement) void document.exitFullscreen()
  else void document.documentElement.requestFullscreen?.()
}
</script>

<template>
  <div>
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="font-display text-2xl font-semibold text-brand-900">Kitchen display</h1>
        <p class="text-sm text-ink-muted">Tap a dish when it is done. Tickets turn amber and then red as they wait.</p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <button
          class="rounded-full border px-3 py-1 text-xs font-semibold"
          :class="soundOn ? 'border-emerald-400 bg-emerald-100 text-emerald-900' : 'border-brand-200 bg-white text-ink-muted'"
          :aria-pressed="soundOn"
          data-testid="sound-toggle"
          @click="toggleSound"
        >
          {{ soundOn ? '🔔 Sound on' : '🔕 Sound off' }}
        </button>
        <button class="rounded-full border border-brand-200 bg-white px-3 py-1 text-xs font-semibold text-ink-muted" @click="fullscreen">Full screen</button>
        <span
          class="inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-semibold"
          :class="connection === 'live' ? 'bg-emerald-100 text-emerald-900' : 'bg-amber-100 text-amber-900'"
          role="status"
          data-testid="connection-status"
        >
          <span class="h-2 w-2 rounded-full" :class="connection === 'live' ? 'bg-emerald-500' : 'animate-pulse bg-amber-500'" />
          {{ connection === 'live' ? 'Live' : connection === 'closed' ? 'Offline — refreshing every 15s' : 'Reconnecting…' }}
        </span>
      </div>
    </div>

    <div class="mt-4 flex flex-wrap gap-2" role="tablist" aria-label="Station">
      <button
        v-for="s in [{ key: null, label: 'All stations' }, ...STATIONS]"
        :key="String(s.key)"
        role="tab"
        :aria-selected="station === s.key"
        class="rounded-full px-4 py-1.5 text-sm font-semibold"
        :class="station === s.key ? 'bg-brand-700 text-white' : 'bg-brand-100 text-brand-900'"
        @click="station = s.key"
      >
        {{ s.label }}
      </button>
    </div>

    <div v-if="loading" class="mt-6 h-64 animate-pulse rounded-2xl bg-brand-100/60" />

    <div v-else class="mt-4 grid gap-6 xl:grid-cols-[1fr_18rem]">
      <div>
        <p v-if="!todo.length" class="rounded-2xl border border-dashed border-brand-200 p-10 text-center text-ink-muted">Nothing to make right now.</p>
        <div class="grid items-start gap-4 md:grid-cols-2 2xl:grid-cols-3">
          <KitchenTicket
            v-for="t in todo"
            :key="t.order.id"
            :ticket="t"
            :now="now"
            :busy="busy"
            @bump-item="bump"
            @recall-item="recall"
            @bump-all="bumpAll(t.order)"
          />
        </div>

        <section v-if="finished.length" class="mt-8">
          <h2 class="mb-3 text-sm font-semibold uppercase tracking-wide text-ink-muted">Done{{ station ? ' here' : '' }} ({{ finished.length }})</h2>
          <div class="grid items-start gap-4 md:grid-cols-2 2xl:grid-cols-3">
            <KitchenTicket
              v-for="t in finished"
              :key="t.order.id"
              :ticket="t"
              :now="now"
              :busy="busy"
              :can-complete="station === null && t.order.status === 'READY'"
              @recall-item="recall"
              @complete="complete(t.order)"
            />
          </div>
        </section>
      </div>

      <aside class="space-y-6">
        <section class="rounded-2xl border border-brand-100 bg-surface-elevated p-4">
          <h2 class="font-semibold text-brand-900">Still to make</h2>
          <p v-if="!counts.length" class="mt-2 text-sm text-ink-subtle">Nothing open.</p>
          <ul class="mt-2 divide-y divide-brand-100">
            <li v-for="c in counts" :key="c.menuItemId" class="flex items-center justify-between gap-2 py-2">
              <span class="text-sm"><strong class="mr-1 text-lg text-brand-800">{{ c.quantity }}×</strong>{{ c.name }}</span>
              <button class="rounded-md border border-red-300 px-2 py-0.5 text-xs font-bold text-red-700 hover:bg-red-50" :aria-label="`86 ${c.name}`" @click="eightySix(c.menuItemId, c.name)">86</button>
            </li>
          </ul>
        </section>

        <section v-if="soldOut.length" class="rounded-2xl border border-red-200 bg-red-50/50 p-4">
          <h2 class="font-semibold text-red-900">Sold out ({{ soldOut.length }})</h2>
          <ul class="mt-2 divide-y divide-red-100">
            <li v-for="m in soldOut" :key="m.id" class="flex items-center justify-between gap-2 py-2 text-sm">
              <span>{{ m.name }}</span>
              <button class="rounded-md border border-brand-300 bg-white px-2 py-0.5 text-xs font-semibold text-brand-800" @click="bringBack(m)">Bring back</button>
            </li>
          </ul>
        </section>
      </aside>
    </div>
  </div>
</template>
