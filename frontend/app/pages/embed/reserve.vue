<script setup lang="ts">
// A compact booking widget meant to be embedded (<iframe>) on a restaurant's own external site —
// same search → pick → confirm flow as /reserve, with the site chrome stripped out and nothing to
// navigate away to. Signing in opens in a new tab so the small iframe never has to host a full
// login page.
import type { AvailableTable, FloorTable } from '~/types/reservation'
import { createReservation, fetchReservationAvailability } from '~/services/reservations'
import { formatTimeRange, formatWhen, localInputToIso, roundUpToStep, toLocalInput } from '~/utils/datetime'

definePageMeta({ layout: 'table', middleware: [] })

const auth = useAuthStore()
const restaurant = useRestaurantStore()

await restaurant.load()

const partySize = ref(2)
const durationMinutes = ref(90)
const startsLocal = ref('')
const minStart = ref('')
const selectedTableId = ref<number | null>(null)
const available = ref<AvailableTable[]>([])
const floor = ref<FloorTable[]>([])
const suggestions = ref<string[]>([])
const searched = ref(false)
const searching = ref(false)
const booking = ref(false)
const error = ref('')
const guestName = ref('')
const guestPhone = ref('')
const lastBooked = ref<{ table_number?: string | null, starts_at: string, ends_at: string, party_size: number } | null>(null)

const minParty = computed(() => restaurant.current?.min_party_size ?? 1)
const maxParty = computed(() => restaurant.current?.max_party_size ?? 20)
const partyValid = computed(() => Number.isInteger(partySize.value) && partySize.value >= minParty.value && partySize.value <= maxParty.value)
const selectedTable = computed(() => floor.value.find(t => t.id === selectedTableId.value) ?? null)
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

watch([startsLocal, partySize, durationMinutes], () => {
  if (!searched.value) return
  available.value = []
  floor.value = []
  suggestions.value = []
  selectedTableId.value = null
  searched.value = false
  error.value = ''
})

onMounted(() => {
  startsLocal.value = toLocalInput(roundUpToStep(new Date(Date.now() + 60 * 60000), 30))
  const leadMinutes = restaurant.current?.booking_lead_time_minutes ?? 0
  minStart.value = toLocalInput(roundUpToStep(new Date(Date.now() + leadMinutes * 60000), 15))
  partySize.value = Math.min(Math.max(partySize.value, minParty.value), maxParty.value ?? partySize.value)
})

async function searchTables() {
  if (!restaurant.current) return
  error.value = ''
  if (!startsLocal.value) {
    error.value = 'Choose a date and time'
    return
  }
  if (!partyValid.value) {
    error.value = `Party size must be between ${minParty.value} and ${maxParty.value}`
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
    floor.value = result.floor ?? []
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
    floor.value = []
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
  if (!restaurant.current || !selectedTableId.value || !auth.isAuthenticated) return
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
    selectedTableId.value = null
    available.value = []
    floor.value = []
    suggestions.value = []
    searched.value = false
  }
  catch (err) {
    error.value = err instanceof Error ? err.message : 'Booking failed'
    await searchTables() // someone may have taken the table while this was open
  }
  finally {
    booking.value = false
  }
}

const loginUrl = `/login?redirect=${encodeURIComponent('/embed/reserve')}`
</script>

<template>
  <div class="mx-auto max-w-lg px-4 py-6">
    <h1 class="font-display text-xl font-semibold text-brand-900">Reserve a table</h1>

    <section v-if="lastBooked" class="mt-4 rounded-xl border border-green-200 bg-green-50 p-4" role="status">
      <p class="font-semibold text-green-900">You're booked!</p>
      <p class="mt-1 text-sm text-green-900">
        {{ formatWhen(lastBooked.starts_at) }} ({{ formatTimeRange(lastBooked.starts_at, lastBooked.ends_at) }}) · party of {{ lastBooked.party_size }}
      </p>
      <button type="button" class="mt-2 text-sm font-medium text-green-900 underline" @click="lastBooked = null">Book another</button>
    </section>

    <template v-else>
      <form class="mt-4 grid gap-3" @submit.prevent="searchTables">
        <label class="block text-sm">
          <span class="mb-1 block font-medium">Party size</span>
          <input v-model.number="partySize" type="number" :min="minParty" :max="maxParty" required class="w-full rounded-lg border border-brand-200 px-3 py-2">
        </label>
        <label class="block text-sm">
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
        <AppButton type="submit" :disabled="searching">{{ searching ? 'Checking…' : 'Show available tables' }}</AppButton>
      </form>

      <section v-if="searched && available.length" class="mt-5">
        <h2 class="text-sm font-semibold text-ink">Choose a table</h2>
        <div class="mt-2 grid grid-cols-2 gap-2">
          <button
            v-for="table in available" :key="table.id" type="button"
            class="rounded-lg border-2 px-3 py-3 text-center transition"
            :class="selectedTableId === table.id ? 'border-brand-700 bg-brand-50' : 'border-brand-100 bg-white hover:border-brand-300'"
            :aria-pressed="selectedTableId === table.id"
            @click="selectedTableId = table.id"
          >
            <p class="font-display font-semibold text-brand-900">{{ table.table_number }}</p>
            <p class="text-xs text-ink-subtle">Seats {{ table.capacity }}</p>
          </button>
        </div>

        <div v-if="selectedTable" class="mt-4 space-y-2 border-t border-brand-100 pt-4">
          <p class="text-sm text-ink-muted">
            <strong class="text-ink">Table {{ selectedTable.table_number }}</strong> · {{ formatTimeRange(startsIso, endsIso) }}
          </p>
          <template v-if="auth.isAuthenticated">
            <input v-model="guestName" required placeholder="Name for reservation" class="w-full rounded-lg border border-brand-200 px-3 py-2 text-sm">
            <input v-model="guestPhone" placeholder="Phone (optional)" class="w-full rounded-lg border border-brand-200 px-3 py-2 text-sm">
            <AppButton :disabled="booking" @click="bookTable">{{ booking ? 'Booking…' : 'Confirm reservation' }}</AppButton>
          </template>
          <p v-else class="text-sm text-ink-muted">
            <a :href="loginUrl" target="_blank" rel="noopener" class="font-medium text-brand-700 underline">Sign in</a>
            to confirm — opens in a new tab.
          </p>
        </div>
      </section>

      <p v-if="error" class="mt-3 text-sm" :class="suggestions.length ? 'text-amber-800' : 'text-red-600'" role="alert">{{ error }}</p>
      <div v-if="suggestions.length" class="mt-2 flex flex-wrap gap-2">
        <button
          v-for="iso in suggestions" :key="iso" type="button"
          class="rounded-full border border-brand-300 bg-white px-3 py-1 text-xs font-medium text-brand-800 hover:bg-brand-50"
          @click="useSuggestion(iso)"
        >
          {{ formatWhen(iso) }}
        </button>
      </div>
    </template>

    <p class="mt-6 text-center text-xs text-ink-subtle">
      Powered by <a :href="`/`" target="_blank" rel="noopener" class="underline">{{ restaurant.current?.name }}</a>
    </p>
  </div>
</template>
