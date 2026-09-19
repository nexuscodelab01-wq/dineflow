<script setup lang="ts">
import { useIntervalFn } from '@vueuse/core'
import type { RestaurantTable } from '~/types/menu'
import type { TableReservationBrief } from '~/types/reservation'
import { fetchAdminTables, updateTableStatus } from '~/services/admin'
import { extendAdminReservation } from '~/services/reservations'
import { formatTimeRange } from '~/utils/datetime'

definePageMeta({ layout: 'admin', middleware: ['staff'] })

const admin = useAdminStore()
const ui = useUiStore()
const tables = ref<RestaurantTable[]>([])
const loading = ref(true)
const error = ref('')
const busyId = ref<number | null>(null)
const filter = ref<string>('ALL')

async function load(silent = false) {
  await admin.initialize()
  if (!admin.restaurantId) return
  try {
    tables.value = await fetchAdminTables(admin.restaurantId)
    error.value = ''
  }
  catch (err) {
    if (!silent) error.value = err instanceof Error ? err.message : 'Could not load tables'
  }
  finally {
    loading.value = false
  }
}

onMounted(() => load())
// Statuses follow the clock (bookings come into range / lapse), so keep the board fresh.
useIntervalFn(() => load(true), 30000)

const STATUSES = ['AVAILABLE', 'RESERVED', 'OCCUPIED', 'CLEANING'] as const

const counts = computed(() => {
  const out: Record<string, number> = { ALL: tables.value.length, AVAILABLE: 0, RESERVED: 0, OCCUPIED: 0, CLEANING: 0 }
  for (const t of tables.value) out[t.status] = (out[t.status] ?? 0) + 1
  return out
})

const shown = computed(() =>
  filter.value === 'ALL' ? tables.value : tables.value.filter(t => t.status === filter.value),
)

function blocking(table: RestaurantTable): TableReservationBrief[] {
  return (table.reservations ?? []).filter(r => r.blocking)
}

function later(table: RestaurantTable): TableReservationBrief[] {
  return (table.reservations ?? []).filter(r => !r.blocking)
}

function statusColor(status: string) {
  if (status === 'AVAILABLE') return 'bg-green-50 text-green-900 border-green-200'
  if (status === 'OCCUPIED') return 'bg-red-50 text-red-900 border-red-200'
  if (status === 'RESERVED') return 'bg-amber-50 text-amber-900 border-amber-200'
  return 'bg-gray-50 text-gray-700 border-gray-200'
}

function describe(r: TableReservationBrief) {
  return `${r.guest_name} (party of ${r.party_size}, ${formatTimeRange(r.starts_at, r.ends_at)})`
}

async function extend(table: RestaurantTable, r: TableReservationBrief, minutes: number) {
  if (!admin.restaurantId || busyId.value !== null) return
  busyId.value = table.id
  try {
    await extendAdminReservation(admin.restaurantId, r.id, minutes)
    ui.success(`${r.guest_name} given ${minutes} more minutes at table ${table.table_number}`)
    await load(true)
  }
  catch (err) {
    // e.g. the next booking is in the way — the message says who; they can be moved from Reservations.
    ui.error(err instanceof Error ? err.message : 'Could not extend')
  }
  finally {
    busyId.value = null
  }
}

/**
 * Releasing (Available) or cleaning a table that a booking is holding needs confirmation:
 * seated parties are marked completed, imminent bookings are cancelled.
 */
async function setStatus(table: RestaurantTable, status: 'AVAILABLE' | 'CLEANING') {
  if (!admin.restaurantId || busyId.value !== null) return
  const holding = blocking(table)
  const label = status === 'AVAILABLE' ? 'available' : 'cleaning'
  let force = false

  if (holding.length) {
    const seated = holding.filter(r => r.status === 'SEATED')
    const upcoming = holding.filter(r => r.status !== 'SEATED')
    const parts: string[] = []
    if (seated.length) parts.push(`Seated: ${seated.map(describe).join('; ')} — will be marked completed.`)
    if (upcoming.length) parts.push(`Reserved: ${upcoming.map(describe).join('; ')} — will be cancelled.`)
    const ok = await ui.confirm({
      title: `Mark table ${table.table_number} as ${label}?`,
      message: `This table is ${table.status.toLowerCase()} because of an active reservation. ${parts.join(' ')}`,
      confirmLabel: status === 'AVAILABLE' ? 'Make available' : 'Mark cleaning',
      cancelLabel: 'Keep as is',
      destructive: true,
    })
    if (!ok) return
    force = true
  }
  else if (table.status === 'OCCUPIED') {
    const ok = await ui.confirm({
      title: `Mark table ${table.table_number} as ${label}?`,
      message: 'This table is marked as occupied. Confirm the guests have left.',
      confirmLabel: status === 'AVAILABLE' ? 'Make available' : 'Mark cleaning',
    })
    if (!ok) return
  }

  busyId.value = table.id
  try {
    const result = await updateTableStatus(admin.restaurantId, table.id, status, force)
    const notes: string[] = []
    if (result.cancelled_reservations) notes.push(`${result.cancelled_reservations} reservation(s) cancelled`)
    if (result.completed_reservations) notes.push(`${result.completed_reservations} party marked completed`)
    ui.success(`Table ${table.table_number} is now ${label}${notes.length ? ` — ${notes.join(', ')}` : ''}`)
    await load(true)
  }
  catch (err) {
    ui.error(err instanceof Error ? err.message : 'Could not update table')
    await load(true) // someone else may have changed it
  }
  finally {
    busyId.value = null
  }
}
</script>

<template>
  <div>
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h1 class="font-display text-2xl font-semibold text-brand-900">Tables</h1>
        <p class="text-sm text-ink-muted">Live floor view — reserved and occupied follow your bookings</p>
      </div>
      <NuxtLink
        to="/admin/reservations"
        class="rounded-lg border border-brand-200 px-4 py-2 text-sm font-semibold text-brand-800 hover:bg-brand-50"
      >
        Manage reservations
      </NuxtLink>
    </div>

    <div class="mt-4 flex flex-wrap gap-2">
      <button
        type="button"
        class="rounded-full px-3 py-1.5 text-sm font-medium transition"
        :class="filter === 'ALL' ? 'bg-brand-700 text-white' : 'bg-brand-100 text-brand-800 hover:bg-brand-200'"
        @click="filter = 'ALL'"
      >
        All <span class="opacity-70">{{ counts.ALL }}</span>
      </button>
      <button
        v-for="s in STATUSES"
        :key="s"
        type="button"
        class="rounded-full px-3 py-1.5 text-sm font-medium capitalize transition"
        :class="filter === s ? 'bg-brand-700 text-white' : 'bg-brand-100 text-brand-800 hover:bg-brand-200'"
        @click="filter = s"
      >
        {{ s.toLowerCase() }} <span class="opacity-70">{{ counts[s] }}</span>
      </button>
    </div>

    <ErrorState v-if="error" class="mt-6" :message="error" @retry="load()" />

    <div v-else-if="loading" class="mt-6 h-40 animate-pulse rounded-2xl bg-brand-100/60" />

    <EmptyState v-else-if="!shown.length" class="mt-6" title="No tables here" description="Try another filter." />

    <div v-else class="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      <article
        v-for="table in shown"
        :key="table.id"
        class="flex flex-col rounded-2xl border-2 p-5"
        :class="statusColor(table.status)"
      >
        <div class="flex items-start justify-between gap-2">
          <p class="text-2xl font-bold">Table {{ table.table_number }}</p>
          <span class="text-sm">Seats {{ table.capacity }}</span>
        </div>
        <p class="mt-1 text-xs font-semibold uppercase tracking-wide">{{ table.status }}</p>

        <div class="mt-3 flex-1 space-y-2 text-sm">
          <div v-for="r in blocking(table)" :key="r.id" class="rounded-lg bg-white/70 px-3 py-2">
            <p class="font-medium">
              {{ r.status === 'SEATED' ? 'Seated' : 'Reserved' }} · {{ r.guest_name }}
            </p>
            <p class="text-xs opacity-80">{{ formatTimeRange(r.starts_at, r.ends_at) }} · party of {{ r.party_size }}</p>
            <div v-if="(r.overdue_minutes ?? 0) > 0" class="mt-2">
              <p class="text-xs font-semibold text-red-700">Overdue by {{ r.overdue_minutes }} min</p>
              <div class="mt-1 flex flex-wrap gap-1">
                <button
                  v-for="m in [15, 30]"
                  :key="m"
                  type="button"
                  class="rounded border border-red-200 bg-white px-1.5 py-0.5 text-xs font-medium hover:bg-red-50 disabled:opacity-50"
                  :disabled="busyId === table.id"
                  @click="extend(table, r, m)"
                >
                  +{{ m }} min
                </button>
              </div>
            </div>
          </div>
          <p v-if="!blocking(table).length && table.status === 'OCCUPIED'" class="rounded-lg bg-white/70 px-3 py-2 text-xs">
            Marked occupied by staff (no booking attached).
          </p>
          <div v-if="later(table).length" class="text-xs">
            <p class="font-semibold opacity-80">Later today</p>
            <ul class="mt-0.5 space-y-0.5">
              <li v-for="r in later(table)" :key="r.id" class="truncate opacity-90">
                {{ formatTimeRange(r.starts_at, r.ends_at) }} · {{ r.guest_name }}
              </li>
            </ul>
          </div>
          <p v-if="!(table.reservations ?? []).length && table.status === 'AVAILABLE'" class="text-xs opacity-70">
            No bookings in the next 24 hours.
          </p>
        </div>

        <div class="mt-4 flex flex-wrap gap-2">
          <button
            v-if="table.status !== 'AVAILABLE'"
            type="button"
            class="rounded-lg bg-white px-3 py-1.5 text-xs font-semibold shadow-sm hover:bg-white/80 disabled:opacity-50"
            :disabled="busyId === table.id"
            @click="setStatus(table, 'AVAILABLE')"
          >
            Make available
          </button>
          <button
            v-if="table.status !== 'CLEANING'"
            type="button"
            class="rounded-lg bg-white/70 px-3 py-1.5 text-xs font-semibold hover:bg-white disabled:opacity-50"
            :disabled="busyId === table.id"
            @click="setStatus(table, 'CLEANING')"
          >
            Mark cleaning
          </button>
          <NuxtLink
            v-if="table.status === 'AVAILABLE'"
            :to="{ path: '/admin/reservations', query: { seat: table.id } }"
            class="rounded-lg bg-brand-700 px-3 py-1.5 text-xs font-semibold text-white hover:bg-brand-800"
          >
            Seat walk-in
          </NuxtLink>
        </div>
      </article>
    </div>
  </div>
</template>
