<script setup lang="ts">
import { useDebounceFn, useIntervalFn } from '@vueuse/core'
import type { AdminTableAvailability, Reservation, ReservationStatus, SlotStatus } from '~/types/reservation'
import {
  createAdminReservation,
  extendAdminReservation,
  fetchAdminAvailability,
  fetchAdminReservations,
  updateAdminReservation,
  updateAdminReservationStatus,
} from '~/services/reservations'
import {
  formatDayLabel,
  formatTimeRange,
  localDayRange,
  localInputToIso,
  minutesBetween,
  roundUpToStep,
  shiftDay,
  toLocalDate,
  toLocalInput,
} from '~/utils/datetime'

definePageMeta({ layout: 'admin', middleware: ['staff'] })

type Mode = 'new' | 'walkin' | 'edit'
type Filter = 'all' | 'upcoming' | 'seated' | 'done' | 'cancelled'

const EARLY_SEAT_MINUTES = 60

const admin = useAdminStore()
const ui = useUiStore()
const route = useRoute()
const router = useRouter()

// ---------------------------------------------------------------- day list

const day = ref(toLocalDate(new Date()))
const reservations = ref<Reservation[]>([])
const loading = ref(true)
const listError = ref('')
const filter = ref<Filter>('all')
const now = ref(Date.now())

const isToday = computed(() => day.value === toLocalDate(new Date()))

async function load(silent = false) {
  await admin.initialize()
  if (!admin.restaurantId) return
  if (!silent) loading.value = true
  try {
    reservations.value = await fetchAdminReservations(admin.restaurantId, localDayRange(day.value))
    listError.value = ''
  }
  catch (err) {
    if (!silent) listError.value = err instanceof Error ? err.message : 'Could not load reservations'
  }
  finally {
    loading.value = false
    now.value = Date.now()
  }
}

// Keep the list live — table statuses change as bookings come into range or lapse.
useIntervalFn(() => load(true), 30000)
watch(day, () => load())

const FILTER_GROUPS: Record<Exclude<Filter, 'all'>, ReservationStatus[]> = {
  upcoming: ['HELD', 'CONFIRMED'],
  seated: ['SEATED'],
  done: ['COMPLETED'],
  cancelled: ['CANCELLED', 'EXPIRED'],
}

const counts = computed(() => {
  const out: Record<Filter, number> = { all: reservations.value.length, upcoming: 0, seated: 0, done: 0, cancelled: 0 }
  for (const r of reservations.value) {
    for (const [key, statuses] of Object.entries(FILTER_GROUPS)) {
      if (statuses.includes(r.status)) out[key as Exclude<Filter, 'all'>]++
    }
  }
  return out
})

const visible = computed(() => {
  if (filter.value === 'all') return reservations.value
  return reservations.value.filter(r => FILTER_GROUPS[filter.value as Exclude<Filter, 'all'>].includes(r.status))
})

const filterChips: { key: Filter, label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'upcoming', label: 'Upcoming' },
  { key: 'seated', label: 'Seated' },
  { key: 'done', label: 'Completed' },
  { key: 'cancelled', label: 'Cancelled' },
]

function isActive(r: Reservation) {
  return r.status === 'HELD' || r.status === 'CONFIRMED' || r.status === 'SEATED'
}

function canSeat(r: Reservation) {
  return (r.status === 'CONFIRMED' || r.status === 'HELD')
    && new Date(r.starts_at).getTime() - now.value <= EARLY_SEAT_MINUTES * 60000
}

const overdueCount = computed(() => reservations.value.filter(r => (r.overdue_minutes ?? 0) > 0 && r.status === 'SEATED').length)

function formatOverdue(minutes: number) {
  return minutes >= 60 ? `${Math.floor(minutes / 60)}h ${minutes % 60}m` : `${minutes}m`
}

/** The next active booking on the same table after this one — the one an extension would collide with. */
function nextOnTable(r: Reservation) {
  return reservations.value
    .filter(o => o.id !== r.id && o.table_id === r.table_id && (o.status === 'CONFIRMED' || o.status === 'HELD')
      && new Date(o.starts_at).getTime() >= new Date(r.starts_at).getTime())
    .sort((a, b) => new Date(a.starts_at).getTime() - new Date(b.starts_at).getTime())[0]
}

async function extend(r: Reservation, minutes: number) {
  if (!admin.restaurantId) return
  try {
    await extendAdminReservation(admin.restaurantId, r.id, minutes)
    ui.success(`${r.guest_name} given ${minutes} more minutes`)
    await load(true)
  }
  catch (err) {
    const message = err instanceof Error ? err.message : 'Could not extend'
    const next = nextOnTable(r)
    if (next && /booked next/.test(message)) {
      // Real-world fix: keep the seated guests, move the incoming party to another table.
      const move = await ui.confirm({
        title: 'Next booking is in the way',
        message: `${next.guest_name} (party of ${next.party_size}) is booked at ${formatTimeRange(next.starts_at, next.ends_at)} on this table. Move them to another table so ${r.guest_name} can stay?`,
        confirmLabel: `Move ${next.guest_name}`,
        cancelLabel: 'Not now',
      })
      if (move) openEdit(next)
    }
    else {
      ui.error(message)
    }
  }
}

async function setStatus(r: Reservation, status: ReservationStatus) {
  if (!admin.restaurantId) return
  if (status === 'CANCELLED') {
    const ok = await ui.confirm({
      title: 'Cancel reservation',
      message: `Cancel ${r.guest_name}'s booking for table ${r.table_number} (${formatTimeRange(r.starts_at, r.ends_at)})? The table becomes free for that time.`,
      confirmLabel: 'Cancel reservation',
      cancelLabel: 'Keep it',
      destructive: true,
    })
    if (!ok) return
  }
  try {
    await updateAdminReservationStatus(admin.restaurantId, r.id, status)
    ui.success(
      status === 'SEATED' ? `${r.guest_name} seated at table ${r.table_number}`
        : status === 'COMPLETED' ? `Table ${r.table_number} is free again`
          : 'Reservation cancelled',
    )
    await load(true)
  }
  catch (err) {
    ui.error(err instanceof Error ? err.message : 'Update failed')
  }
}

// ---------------------------------------------------------------- booking form (new / walk-in / edit)

const showForm = ref(false)
const mode = ref<Mode>('new')
const editing = ref<Reservation | null>(null)
const form = reactive({
  startsLocal: '',
  duration: 90,
  party: 2,
  table_id: 0,
  guest_name: '',
  guest_phone: '',
  guest_email: '',
  notes: '',
  seatNow: false,
})
const availability = ref<AdminTableAvailability[]>([])
const checking = ref(false)
const availError = ref('')
const formError = ref('')
const tableHint = ref('')
const saving = ref(false)

// Seated guests can't be moved, only their details edited.
const scheduleLocked = computed(() => mode.value === 'edit' && editing.value?.status === 'SEATED')
const partySize = computed(() => Math.min(20, Math.max(1, Math.floor(Number(form.party)) || 1)))
// `min` must sit on the 15-minute grid: datetime-local measures `step` from `min`.
const minStart = computed(() => toLocalInput(roundUpToStep(new Date(now.value - 5 * 60000), 15)))

const nearNow = computed(() => {
  if (mode.value !== 'new' || !form.startsLocal) return false
  const diff = new Date(form.startsLocal).getTime() - Date.now()
  return diff <= 30 * 60000
})

const formTitle = computed(() => ({
  new: 'New reservation',
  walkin: 'Seat walk-in',
  edit: 'Edit reservation',
}[mode.value]))

const selectedTable = computed(() => availability.value.find(t => t.id === form.table_id))

let checkSeq = 0
async function runCheck() {
  if (!admin.restaurantId || !form.startsLocal || scheduleLocked.value) return
  const seq = ++checkSeq
  checking.value = true
  availError.value = ''
  try {
    const startsAt = mode.value === 'walkin' ? new Date().toISOString() : localInputToIso(form.startsLocal)
    const result = await fetchAdminAvailability(admin.restaurantId, {
      starts_at: startsAt,
      party_size: partySize.value,
      duration_minutes: form.duration,
      exclude_reservation_id: editing.value?.id,
    })
    if (seq !== checkSeq) return // a newer check superseded this one
    availability.value = result.tables

    if (form.table_id) {
      const current = result.tables.find(t => t.id === form.table_id)
      if (!current || !current.available) {
        tableHint.value = current
          ? `Table ${current.table_number} isn't free at that time — please pick another.`
          : ''
        form.table_id = 0
      }
    }
  }
  catch (err) {
    if (seq === checkSeq) availError.value = err instanceof Error ? err.message : 'Could not check availability'
  }
  finally {
    if (seq === checkSeq) checking.value = false
  }
}

const debouncedCheck = useDebounceFn(runCheck, 300)

watch(() => [form.startsLocal, form.duration, form.party], () => {
  if (showForm.value) debouncedCheck()
})

function resetForm() {
  Object.assign(form, {
    startsLocal: '',
    duration: 90,
    party: 2,
    table_id: 0,
    guest_name: '',
    guest_phone: '',
    guest_email: '',
    notes: '',
    seatNow: false,
  })
  availability.value = []
  availError.value = ''
  formError.value = ''
  tableHint.value = ''
}

function defaultStartForDay() {
  if (isToday.value) return toLocalInput(roundUpToStep(new Date(Date.now() + 30 * 60000), 15))
  return `${day.value}T19:00`
}

function openNew() {
  resetForm()
  mode.value = 'new'
  editing.value = null
  form.startsLocal = defaultStartForDay()
  showForm.value = true
  runCheck()
}

function openWalkIn(tableId = 0) {
  resetForm()
  mode.value = 'walkin'
  editing.value = null
  form.startsLocal = toLocalInput(new Date())
  form.seatNow = true
  form.table_id = tableId
  showForm.value = true
  runCheck()
}

function openEdit(r: Reservation) {
  resetForm()
  mode.value = 'edit'
  editing.value = r
  form.startsLocal = toLocalInput(new Date(r.starts_at))
  form.duration = minutesBetween(r.starts_at, r.ends_at)
  form.party = r.party_size
  form.table_id = r.table_id
  form.guest_name = r.guest_name
  form.guest_phone = r.guest_phone || ''
  form.guest_email = r.guest_email || ''
  form.notes = r.notes || ''
  showForm.value = true
  runCheck()
}

function closeForm() {
  if (saving.value) return
  showForm.value = false
}

const DURATION_OPTIONS = [60, 90, 120, 150, 180]
const durationOptions = computed(() =>
  DURATION_OPTIONS.includes(form.duration) ? DURATION_OPTIONS : [...DURATION_OPTIONS, form.duration].sort((a, b) => a - b),
)

const slotStyles: Record<SlotStatus, string> = {
  AVAILABLE: 'border-green-200 bg-green-50 hover:border-green-500',
  RESERVED: 'border-amber-200 bg-amber-50 cursor-not-allowed',
  OCCUPIED: 'border-red-200 bg-red-50 cursor-not-allowed',
  CLEANING: 'border-slate-200 bg-slate-50 cursor-not-allowed',
  TOO_SMALL: 'border-gray-200 bg-gray-50 opacity-60 cursor-not-allowed',
}
const slotLabels: Record<SlotStatus, string> = {
  AVAILABLE: 'Available',
  RESERVED: 'Reserved',
  OCCUPIED: 'Occupied',
  CLEANING: 'Cleaning',
  TOO_SMALL: 'Too small',
}

function pickTable(t: AdminTableAvailability) {
  if (!t.available) return
  form.table_id = t.id
  tableHint.value = ''
}

async function save() {
  if (!admin.restaurantId) return
  formError.value = ''
  if (!form.guest_name.trim()) {
    formError.value = 'Guest name is required'
    return
  }
  if (!form.startsLocal) {
    formError.value = 'Choose a date and time'
    return
  }
  if (!scheduleLocked.value && !form.table_id) {
    formError.value = 'Pick an available table'
    return
  }

  saving.value = true
  try {
    let saved: Reservation
    if (mode.value === 'edit' && editing.value) {
      saved = await updateAdminReservation(admin.restaurantId, editing.value.id, {
        ...(scheduleLocked.value
          ? {}
          : {
              table_id: form.table_id,
              party_size: partySize.value,
              starts_at: localInputToIso(form.startsLocal),
              duration_minutes: form.duration,
            }),
        guest_name: form.guest_name.trim(),
        guest_phone: form.guest_phone,
        guest_email: form.guest_email || undefined,
        notes: form.notes,
      })
      ui.success('Reservation updated')
    }
    else {
      saved = await createAdminReservation(admin.restaurantId, {
        table_id: form.table_id,
        party_size: partySize.value,
        starts_at: mode.value === 'walkin' ? new Date().toISOString() : localInputToIso(form.startsLocal),
        duration_minutes: form.duration,
        guest_name: form.guest_name.trim(),
        guest_phone: form.guest_phone || undefined,
        guest_email: form.guest_email || undefined,
        notes: form.notes || undefined,
        seat_immediately: mode.value === 'walkin' || form.seatNow,
      })
      ui.success(saved.status === 'SEATED'
        ? `${saved.guest_name} seated at table ${saved.table_number}`
        : `Table ${saved.table_number} reserved for ${saved.guest_name}`)
    }
    showForm.value = false
    // Jump to the booking's day so it's visible straight away.
    const savedDay = toLocalDate(new Date(saved.starts_at))
    if (savedDay !== day.value) day.value = savedDay
    else await load(true)
  }
  catch (err) {
    formError.value = err instanceof Error ? err.message : 'Could not save reservation'
    // The slot may have been taken meanwhile — refresh what's free.
    runCheck()
  }
  finally {
    saving.value = false
  }
}

onMounted(async () => {
  await load()
  // Deep link from the Tables page: /admin/reservations?seat=<tableId>
  const seat = Number(route.query.seat)
  if (seat) {
    openWalkIn(seat)
    router.replace({ query: {} })
  }
})
</script>

<template>
  <div>
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h1 class="font-display text-2xl font-semibold text-brand-900">Reservations</h1>
        <p class="text-sm text-ink-muted">Book tables for any date, and seat walk-ins</p>
      </div>
      <div class="flex flex-wrap gap-2">
        <AppButton @click="openNew">New reservation</AppButton>
        <button
          type="button"
          class="rounded-lg border border-brand-200 px-4 py-2 text-sm font-semibold text-brand-800 hover:bg-brand-50"
          @click="openWalkIn()"
        >
          Seat walk-in
        </button>
      </div>
    </div>

    <!-- Day navigation -->
    <div class="mt-5 flex flex-wrap items-center gap-2">
      <button type="button" class="rounded-lg border border-brand-200 px-3 py-2 text-sm hover:bg-brand-50" aria-label="Previous day" @click="day = shiftDay(day, -1)">‹</button>
      <input
        v-model="day"
        type="date"
        class="rounded-lg border border-brand-200 bg-white px-3 py-2 text-sm"
        aria-label="Reservation date"
      >
      <button type="button" class="rounded-lg border border-brand-200 px-3 py-2 text-sm hover:bg-brand-50" aria-label="Next day" @click="day = shiftDay(day, 1)">›</button>
      <button
        v-if="!isToday"
        type="button"
        class="rounded-lg px-3 py-2 text-sm font-medium text-brand-700 hover:bg-brand-50"
        @click="day = toLocalDate(new Date())"
      >
        Today
      </button>
      <span class="ml-1 text-sm font-medium text-ink">{{ formatDayLabel(day) }}</span>
    </div>

    <p
      v-if="overdueCount"
      class="mt-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800"
      role="status"
    >
      {{ overdueCount }} {{ overdueCount === 1 ? 'party is' : 'parties are' }} past their booked time. Extend them, or mark them complete once they leave.
    </p>

    <div class="mt-4 flex flex-wrap gap-2">
      <button
        v-for="chip in filterChips"
        :key="chip.key"
        type="button"
        class="rounded-full px-3 py-1.5 text-sm font-medium transition"
        :class="filter === chip.key ? 'bg-brand-700 text-white' : 'bg-brand-100 text-brand-800 hover:bg-brand-200'"
        @click="filter = chip.key"
      >
        {{ chip.label }} <span class="opacity-70">{{ counts[chip.key] }}</span>
      </button>
    </div>

    <ErrorState v-if="listError" class="mt-6" :message="listError" @retry="load()" />

    <LoadingState v-else-if="loading" class="mt-6" :rows="1" />

    <EmptyState
      v-else-if="!visible.length"
      class="mt-6"
      :title="reservations.length ? 'Nothing in this view' : `No reservations on ${formatDayLabel(day)}`"
      :description="reservations.length ? 'Try another filter.' : 'Use “New reservation” to book a table, or “Seat walk-in” for guests who are here now.'"
    />

    <div v-else class="mt-6 overflow-x-auto rounded-2xl border border-brand-100 bg-surface-elevated">
      <table class="min-w-full text-left text-sm">
        <thead class="border-b border-brand-100 bg-brand-50/50 text-xs uppercase tracking-wide text-ink-subtle">
          <tr>
            <th class="px-4 py-3">Time</th>
            <th class="px-4 py-3">Guest</th>
            <th class="px-4 py-3">Table</th>
            <th class="px-4 py-3">Party</th>
            <th class="px-4 py-3">Status</th>
            <th class="px-4 py-3">Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in visible" :key="r.id" class="border-b border-brand-50" :class="{ 'opacity-60': !isActive(r) }">
            <td class="whitespace-nowrap px-4 py-3">{{ formatTimeRange(r.starts_at, r.ends_at) }}</td>
            <td class="px-4 py-3">
              <div class="font-medium">{{ r.guest_name }}</div>
              <div class="text-xs text-ink-subtle">{{ r.guest_phone || r.guest_email }}</div>
              <div v-if="r.notes" class="mt-0.5 max-w-xs truncate text-xs italic text-ink-subtle" :title="r.notes">“{{ r.notes }}”</div>
            </td>
            <td class="px-4 py-3">{{ r.table_number }}</td>
            <td class="px-4 py-3">{{ r.party_size }}</td>
            <td class="px-4 py-3">
              <StatusBadge :status="r.status" />
              <p v-if="(r.overdue_minutes ?? 0) > 0" class="mt-1 text-xs font-semibold text-red-700">
                Overdue {{ formatOverdue(r.overdue_minutes!) }}
              </p>
              <p v-if="r.blocked_by" class="mt-1 max-w-[14rem] text-xs font-medium text-red-700">
                Table still occupied by {{ r.blocked_by }}
              </p>
              <NuxtLink v-if="r.order_id" :to="`/admin/orders/${r.order_id}`" class="mt-1 block text-xs text-brand-700 hover:underline">Order placed</NuxtLink>
            </td>
            <td class="space-x-3 whitespace-nowrap px-4 py-3">
              <button
                v-if="r.status === 'CONFIRMED' || r.status === 'HELD'"
                class="text-brand-700 hover:underline disabled:cursor-not-allowed disabled:no-underline disabled:opacity-40"
                :disabled="!canSeat(r)"
                :title="canSeat(r) ? 'Guests have arrived' : `Seating opens ${EARLY_SEAT_MINUTES} minutes before the booking`"
                @click="setStatus(r, 'SEATED')"
              >
                Seat
              </button>
              <button v-if="r.status === 'SEATED'" class="text-brand-700 hover:underline" @click="setStatus(r, 'COMPLETED')">
                Complete
              </button>
              <template v-if="r.status === 'SEATED'">
                <button
                  v-for="m in [15, 30, 60]"
                  :key="m"
                  class="rounded border border-brand-200 px-1.5 py-0.5 text-xs text-brand-800 hover:bg-brand-50"
                  :title="`Give ${r.guest_name} ${m} more minutes`"
                  @click="extend(r, m)"
                >
                  +{{ m }}m
                </button>
              </template>
              <button v-if="isActive(r)" class="text-brand-700 hover:underline" @click="openEdit(r)">Edit</button>
              <button v-if="r.status === 'CONFIRMED' || r.status === 'HELD'" class="text-red-600 hover:underline" @click="setStatus(r, 'CANCELLED')">
                Cancel
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Booking modal -->
    <div
      v-if="showForm"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
      @click.self="closeForm"
      @keydown.esc="closeForm"
    >
      <div class="max-h-[92vh] w-full max-w-2xl overflow-y-auto rounded-2xl bg-white p-6 shadow-xl">
        <div class="flex items-start justify-between gap-4">
          <div>
            <h2 class="font-display text-xl font-semibold text-brand-900">{{ formTitle }}</h2>
            <p v-if="mode === 'walkin'" class="text-sm text-ink-muted">Seats the party at a free table right now.</p>
            <p v-else-if="scheduleLocked" class="text-sm text-ink-muted">These guests are seated — only their details can be changed.</p>
          </div>
          <button type="button" class="rounded-lg p-1 text-xl leading-none text-ink-muted hover:bg-brand-50" aria-label="Close" @click="closeForm">×</button>
        </div>

        <form class="mt-5 space-y-5" @submit.prevent="save">
          <section v-if="!scheduleLocked" class="space-y-3">
            <h3 class="text-sm font-semibold text-ink">When &amp; how many</h3>
            <div class="grid gap-3 sm:grid-cols-3">
              <label v-if="mode !== 'walkin'" class="block text-sm sm:col-span-2">
                <span class="mb-1 block font-medium">Date &amp; time</span>
                <input
                  v-model="form.startsLocal"
                  type="datetime-local"
                  :step="mode === 'edit' ? 60 : 900"
                  required
                  :min="mode === 'new' ? minStart : undefined"
                  class="w-full rounded-lg border border-brand-200 px-3 py-2"
                >
              </label>
              <div v-else class="text-sm sm:col-span-2">
                <span class="mb-1 block font-medium">Time</span>
                <p class="rounded-lg bg-brand-50 px-3 py-2 text-ink-muted">Now</p>
              </div>
              <label class="block text-sm">
                <span class="mb-1 block font-medium">Party size</span>
                <input v-model.number="form.party" type="number" min="1" max="20" required class="w-full rounded-lg border border-brand-200 px-3 py-2">
              </label>
              <label class="block text-sm">
                <span class="mb-1 block font-medium">Duration</span>
                <select v-model.number="form.duration" class="w-full rounded-lg border border-brand-200 px-3 py-2">
                  <option v-for="m in durationOptions" :key="m" :value="m">
                    {{ m % 60 === 0 ? `${m / 60} hour${m === 60 ? '' : 's'}` : `${Math.floor(m / 60)}h ${m % 60}m` }}
                  </option>
                </select>
              </label>
              <label v-if="mode === 'new' && nearNow" class="flex items-end gap-2 pb-2 text-sm sm:col-span-2">
                <input v-model="form.seatNow" type="checkbox" class="h-4 w-4">
                <span>Guests are here — seat them immediately</span>
              </label>
            </div>
          </section>

          <section v-if="!scheduleLocked" class="space-y-3">
            <div class="flex items-center justify-between">
              <h3 class="text-sm font-semibold text-ink">Table</h3>
              <span v-if="checking" class="text-xs text-ink-subtle">Checking availability…</span>
              <span v-else-if="selectedTable" class="text-xs text-brand-700">Selected: {{ selectedTable.table_number }}</span>
            </div>
            <p v-if="mode !== 'walkin'" class="text-xs text-ink-subtle">
              Status shown is for the chosen date, time and duration — not the table's status right now.
              <template v-if="admin.restaurant?.reservation_buffer_minutes">
                A {{ admin.restaurant.reservation_buffer_minutes }}-minute reset gap is kept between bookings on the same table.
              </template>
            </p>
            <p v-if="tableHint" class="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900">{{ tableHint }}</p>
            <p v-if="availError" class="text-sm text-red-600">{{ availError }}</p>

            <div class="grid grid-cols-2 gap-2 sm:grid-cols-3">
              <button
                v-for="t in availability"
                :key="t.id"
                type="button"
                class="rounded-xl border-2 p-3 text-left transition"
                :class="[slotStyles[t.slot_status], form.table_id === t.id ? 'ring-2 ring-brand-700 ring-offset-1' : '']"
                :disabled="!t.available"
                :aria-pressed="form.table_id === t.id"
                @click="pickTable(t)"
              >
                <div class="flex items-baseline justify-between gap-2">
                  <span class="font-display text-lg font-semibold text-brand-900">{{ t.table_number }}</span>
                  <span class="text-xs text-ink-subtle">Seats {{ t.capacity }}</span>
                </div>
                <p class="mt-1 text-xs font-semibold uppercase tracking-wide"
                   :class="t.available ? 'text-green-800' : 'text-ink-muted'">
                  {{ slotLabels[t.slot_status] }}
                </p>
                <ul v-if="t.conflicts.length" class="mt-1 space-y-0.5 text-xs text-ink-muted">
                  <li v-for="c in t.conflicts.slice(0, 2)" :key="c.id" class="truncate" :title="`${c.guest_name} · party of ${c.party_size}`">
                    {{ formatTimeRange(c.starts_at, c.ends_at) }} · {{ c.guest_name }}
                  </li>
                </ul>
                <p v-else-if="t.slot_status === 'OCCUPIED' || t.slot_status === 'CLEANING'" class="mt-1 text-xs text-ink-muted">
                  {{ t.slot_status === 'CLEANING' ? 'Being cleaned' : 'In use right now' }}
                </p>
              </button>
            </div>
            <p v-if="!checking && !availability.length && !availError" class="text-sm text-ink-subtle">No tables configured.</p>
            <p
              v-else-if="!checking && availability.length && !availability.some(t => t.available)"
              class="text-sm text-amber-800"
            >
              No table is free for that party and time. Try a different time or a shorter duration.
            </p>
          </section>

          <section class="space-y-3">
            <h3 class="text-sm font-semibold text-ink">Guest</h3>
            <div class="grid gap-3 sm:grid-cols-2">
              <input v-model="form.guest_name" required placeholder="Guest name" class="rounded-lg border border-brand-200 px-3 py-2 text-sm sm:col-span-2">
              <input v-model="form.guest_phone" placeholder="Phone" class="rounded-lg border border-brand-200 px-3 py-2 text-sm">
              <input v-model="form.guest_email" type="email" placeholder="Email (optional)" class="rounded-lg border border-brand-200 px-3 py-2 text-sm">
              <textarea v-model="form.notes" rows="2" placeholder="Notes — allergies, occasion, seating preference…" class="rounded-lg border border-brand-200 px-3 py-2 text-sm sm:col-span-2" />
            </div>
          </section>

          <p v-if="formError" class="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">{{ formError }}</p>

          <div class="sticky bottom-0 -mx-6 -mb-6 flex flex-wrap gap-2 border-t border-brand-100 bg-white px-6 py-4">
            <AppButton type="submit" :disabled="saving">
              {{ saving ? 'Saving…' : mode === 'edit' ? 'Save changes' : mode === 'walkin' || form.seatNow ? 'Seat guests' : 'Book table' }}
            </AppButton>
            <button type="button" class="rounded-lg border border-brand-200 px-4 py-2 text-sm hover:bg-brand-50" :disabled="saving" @click="closeForm">
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>
