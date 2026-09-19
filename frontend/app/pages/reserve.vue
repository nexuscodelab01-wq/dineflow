<script setup lang="ts">
import type { AvailableTable, Reservation } from '~/types/reservation'
import {
  cancelReservation,
  createReservation,
  fetchMyReservations,
  fetchReservationAvailability,
} from '~/services/reservations'
import {
  formatTime,
  formatTimeRange,
  formatWhen,
  localInputToIso,
  roundUpToStep,
  toLocalInput,
} from '~/utils/datetime'

definePageMeta({ middleware: [] })

const auth = useAuthStore()
const restaurant = useRestaurantStore()
const ui = useUiStore()

await restaurant.load()

const partySize = ref(2)
const durationMinutes = ref(90)
// Clock-derived defaults are set on mount: the server renders in UTC, the browser in local time.
const startsLocal = ref('')
const minStart = ref('')
const selectedTableId = ref<number | null>(null)
const available = ref<AvailableTable[]>([])
const suggestions = ref<string[]>([])
const searched = ref(false)
const searching = ref(false)
const booking = ref(false)
const error = ref('')
const myReservations = ref<Reservation[]>([])
const showHistory = ref(false)
const guestName = ref('')
const guestPhone = ref('')
const lastBooked = ref<Reservation | null>(null)

const partyValid = computed(() => Number.isInteger(partySize.value) && partySize.value >= 1 && partySize.value <= 20)
const selectedTable = computed(() => available.value.find(t => t.id === selectedTableId.value) ?? null)
const startsIso = computed(() => (startsLocal.value ? localInputToIso(startsLocal.value) : ''))
const endsIso = computed(() =>
  startsLocal.value ? new Date(new Date(startsLocal.value).getTime() + durationMinutes.value * 60000).toISOString() : '',
)

watchEffect(() => {
  if (auth.user) {
    guestName.value = `${auth.user.first_name} ${auth.user.last_name}`.trim()
    guestPhone.value = auth.user.phone || ''
  }
})

// Results belong to the exact date/party/duration that was searched. If any of them change,
// the shown tables may no longer be free, so drop them rather than let someone book a stale slot.
watch([startsLocal, partySize, durationMinutes], () => {
  if (!searched.value) return
  available.value = []
  suggestions.value = []
  selectedTableId.value = null
  searched.value = false
  error.value = ''
})

async function loadMine() {
  if (!auth.isAuthenticated || !restaurant.current) return
  try {
    myReservations.value = await fetchMyReservations(restaurant.current.id, showHistory.value)
  }
  catch {
    myReservations.value = []
  }
}

onMounted(() => {
  startsLocal.value = toLocalInput(roundUpToStep(new Date(Date.now() + 60 * 60000), 30))
  // `min` must sit on the 15-minute grid: datetime-local measures `step` from `min`.
  minStart.value = toLocalInput(roundUpToStep(new Date(), 15))
  loadMine()
})
watch(showHistory, loadMine)

async function searchTables() {
  if (!restaurant.current) return
  error.value = ''
  if (!startsLocal.value) {
    error.value = 'Choose a date and time'
    return
  }
  if (!partyValid.value) {
    error.value = 'Party size must be between 1 and 20'
    return
  }
  selectedTableId.value = null
  searching.value = true
  try {
    const result = await fetchReservationAvailability(restaurant.current.slug, {
      starts_at: localInputToIso(startsLocal.value),
      party_size: partySize.value,
      duration_minutes: durationMinutes.value,
    })
    available.value = result.tables
    suggestions.value = result.suggested_times ?? []
    searched.value = true
    if (!result.tables.length) {
      error.value = suggestions.value.length
        ? 'No tables are free at that time — here are nearby times that are.'
        : 'No tables are free for that party size and time. Try another day.'
    }
  }
  catch (err) {
    available.value = []
    suggestions.value = []
    error.value = err instanceof Error ? err.message : 'Could not check availability'
  }
  finally {
    searching.value = false
  }
}

async function useSuggestion(iso: string) {
  startsLocal.value = toLocalInput(new Date(iso))
  await nextTick()
  await searchTables()
}

async function bookTable() {
  if (!restaurant.current || !selectedTableId.value) return
  if (!auth.isAuthenticated) {
    await navigateTo(`/login?redirect=${encodeURIComponent('/reserve')}`)
    return
  }
  if (!guestName.value.trim()) {
    error.value = 'Please enter a name for the reservation'
    return
  }
  booking.value = true
  error.value = ''
  try {
    const reservation = await createReservation(restaurant.current.slug, {
      table_id: selectedTableId.value,
      party_size: partySize.value,
      starts_at: localInputToIso(startsLocal.value),
      duration_minutes: durationMinutes.value,
      guest_name: guestName.value.trim(),
      guest_email: auth.user?.email,
      guest_phone: guestPhone.value || undefined,
      hold: false,
    })
    lastBooked.value = reservation
    ui.success(`Table ${reservation.table_number} reserved`)
    selectedTableId.value = null
    available.value = []
    suggestions.value = []
    searched.value = false
    await loadMine()
  }
  catch (err) {
    error.value = err instanceof Error ? err.message : 'Booking failed'
    ui.error(error.value)
    // Someone may have taken the table while this page was open — show what's free now.
    await searchTables()
  }
  finally {
    booking.value = false
  }
}

async function cancelMine(r: Reservation) {
  const ok = await ui.confirm({
    title: 'Cancel reservation',
    message: `Cancel your booking for table ${r.table_number} on ${formatWhen(r.starts_at)}?`,
    confirmLabel: 'Cancel reservation',
    cancelLabel: 'Keep it',
    destructive: true,
  })
  if (!ok) return
  try {
    await cancelReservation(r.id)
    ui.success('Reservation cancelled')
    if (lastBooked.value?.id === r.id) lastBooked.value = null
    await loadMine()
  }
  catch (err) {
    ui.error(err instanceof Error ? err.message : 'Cancel failed')
  }
}

function canCancel(r: Reservation) {
  return (r.status === 'CONFIRMED' || r.status === 'HELD') && !r.order_id
}
</script>

<template>
  <div class="mx-auto max-w-3xl px-4 py-8 sm:px-6">
    <h1 class="font-display text-3xl font-semibold text-brand-900">Reserve a table</h1>
    <p class="mt-2 text-ink-muted">
      Choose your party size and time, then pick an available table.
      Walk-ins without a reservation are seated by restaurant staff.
    </p>

    <section
      v-if="lastBooked"
      class="mt-6 rounded-2xl border border-green-200 bg-green-50 p-5"
      role="status"
    >
      <p class="font-semibold text-green-900">You're booked!</p>
      <p class="mt-1 text-sm text-green-900">
        Table {{ lastBooked.table_number }} · {{ formatWhen(lastBooked.starts_at) }} ({{ formatTimeRange(lastBooked.starts_at, lastBooked.ends_at) }}) · party of {{ lastBooked.party_size }}
      </p>
      <div class="mt-3 flex flex-wrap gap-3 text-sm">
        <NuxtLink to="/menu" class="font-medium text-green-900 underline">Browse the menu</NuxtLink>
        <button type="button" class="text-green-900 underline" @click="lastBooked = null">Dismiss</button>
      </div>
    </section>

    <section class="mt-8 rounded-2xl border border-brand-100 bg-surface-elevated p-5">
      <h2 class="font-semibold text-ink">When &amp; how many</h2>
      <form class="mt-4 grid gap-3 sm:grid-cols-3" @submit.prevent="searchTables">
        <label class="block text-sm">
          <span class="mb-1 block font-medium">Party size</span>
          <input v-model.number="partySize" type="number" min="1" max="20" required class="w-full rounded-lg border border-brand-200 px-3 py-2">
        </label>
        <label class="block text-sm sm:col-span-2">
          <span class="mb-1 block font-medium">Date &amp; time</span>
          <input v-model="startsLocal" type="datetime-local" step="900" :min="minStart" required class="w-full rounded-lg border border-brand-200 px-3 py-2">
        </label>
        <label class="block text-sm">
          <span class="mb-1 block font-medium">Duration</span>
          <select v-model.number="durationMinutes" class="w-full rounded-lg border border-brand-200 px-3 py-2">
            <option :value="60">1 hour</option>
            <option :value="90">1.5 hours</option>
            <option :value="120">2 hours</option>
            <option :value="180">3 hours</option>
          </select>
        </label>
        <div class="sm:col-span-3">
          <AppButton type="submit" :disabled="searching">
            {{ searching ? 'Checking…' : 'Show available tables' }}
          </AppButton>
        </div>
      </form>
    </section>

    <section v-if="available.length" class="mt-6 rounded-2xl border border-brand-100 bg-surface-elevated p-5">
      <h2 class="font-semibold text-ink">Available tables</h2>
      <p class="mt-1 text-sm text-ink-muted">
        Free on {{ formatWhen(startsIso) }} for {{ durationMinutes / 60 }}h. Select a table that fits your party.
      </p>
      <div class="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
        <button
          v-for="table in available"
          :key="table.id"
          type="button"
          class="rounded-xl border-2 px-3 py-4 text-center transition"
          :class="selectedTableId === table.id
            ? 'border-brand-700 bg-brand-50 shadow-sm'
            : 'border-brand-100 bg-white hover:border-brand-300'"
          :aria-pressed="selectedTableId === table.id"
          @click="selectedTableId = table.id"
        >
          <p class="font-display text-lg font-semibold text-brand-900">{{ table.table_number }}</p>
          <p class="text-xs text-ink-subtle">Seats {{ table.capacity }}</p>
        </button>
      </div>

      <div v-if="selectedTable" class="mt-5 space-y-3 border-t border-brand-100 pt-5">
        <template v-if="auth.isAuthenticated">
          <p class="text-sm text-ink-muted">
            Table {{ selectedTable.table_number }} · {{ formatTimeRange(startsIso, endsIso) }}
          </p>
          <input v-model="guestName" required placeholder="Name for reservation" class="w-full rounded-lg border border-brand-200 px-3 py-2 text-sm">
          <input v-model="guestPhone" placeholder="Phone" class="w-full rounded-lg border border-brand-200 px-3 py-2 text-sm">
          <AppButton :disabled="booking" @click="bookTable">
            {{ booking ? 'Booking…' : 'Confirm reservation' }}
          </AppButton>
        </template>
        <p v-else class="text-sm text-ink-muted">
          <NuxtLink :to="`/login?redirect=${encodeURIComponent('/reserve')}`" class="font-medium text-brand-700 underline">Sign in</NuxtLink>
          to confirm your reservation.
        </p>
      </div>
    </section>

    <p v-if="error" class="mt-4 text-sm" :class="suggestions.length ? 'text-amber-800' : 'text-red-600'" role="alert">{{ error }}</p>

    <div v-if="suggestions.length" class="mt-3 flex flex-wrap gap-2">
      <button
        v-for="iso in suggestions"
        :key="iso"
        type="button"
        class="rounded-full border border-brand-300 bg-white px-4 py-1.5 text-sm font-medium text-brand-800 hover:bg-brand-50"
        @click="useSuggestion(iso)"
      >
        {{ formatWhen(iso) }}
      </button>
    </div>

    <section v-if="auth.isAuthenticated" class="mt-10">
      <div class="flex items-center justify-between gap-3">
        <h2 class="font-semibold text-ink">{{ showHistory ? 'All your reservations' : 'Your upcoming reservations' }}</h2>
        <button type="button" class="text-sm text-brand-700 hover:underline" @click="showHistory = !showHistory">
          {{ showHistory ? 'Show upcoming only' : 'Show history' }}
        </button>
      </div>

      <p v-if="!myReservations.length" class="mt-3 text-sm text-ink-muted">
        {{ showHistory ? 'No reservations yet.' : 'You have no upcoming reservations.' }}
      </p>

      <ul v-else class="mt-3 space-y-3">
        <li
          v-for="r in myReservations"
          :key="r.id"
          class="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-brand-100 bg-surface-elevated px-4 py-3"
        >
          <div>
            <p class="font-medium">Table {{ r.table_number }} · {{ r.party_size }} guests</p>
            <p class="text-sm text-ink-muted">{{ formatWhen(r.starts_at) }} – {{ formatTime(r.ends_at) }}</p>
          </div>
          <div class="flex items-center gap-3">
            <StatusBadge :status="r.status" />
            <button v-if="canCancel(r)" type="button" class="text-sm text-red-600 hover:underline" @click="cancelMine(r)">
              Cancel
            </button>
            <span v-else-if="r.order_id && (r.status === 'CONFIRMED' || r.status === 'HELD')" class="text-xs text-ink-subtle">
              Order placed — call to change
            </span>
          </div>
        </li>
      </ul>
      <p class="mt-3 text-sm text-ink-subtle">
        Ready to order?
        <NuxtLink to="/menu" class="text-brand-700 underline">Browse the menu</NuxtLink>
        then checkout with dine-in and select this reservation.
      </p>
    </section>
  </div>
</template>
