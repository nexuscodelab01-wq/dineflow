<script setup lang="ts">
import type { RestaurantTable } from '~/types/menu'
import type { WaitlistEntry } from '~/types/reservation'
import { fetchAdminTables } from '~/services/admin'
import { addToWaitlist, cancelWaitlistEntry, fetchWaitlist, notifyWaitlistEntry, seatWaitlistEntry } from '~/services/reservations'

definePageMeta({ layout: 'admin', middleware: ['staff'] })

const admin = useAdminStore()
const ui = useUiStore()

const entries = ref<WaitlistEntry[]>([])
const tables = ref<RestaurantTable[]>([])
const loading = ref(true)
const showForm = ref(false)
const busyId = ref<number | null>(null)
const seatingId = ref<number | null>(null)
const seatTableId = ref<number | null>(null)

const form = reactive({ guestName: '', guestPhone: '', guestEmail: '', partySize: 2, quotedMinutes: null as number | null, notes: '' })
const creating = ref(false)
const formError = ref('')

let refreshTimer: ReturnType<typeof setInterval> | undefined

async function load() {
  if (!admin.restaurantId) return
  const [w, t] = await Promise.all([fetchWaitlist(admin.restaurantId), fetchAdminTables(admin.restaurantId)])
  entries.value = w
  tables.value = t
}

onMounted(async () => {
  await admin.initialize()
  await load()
  loading.value = false
  // The wait time shown for each guest ticks up; a light poll keeps it (and new walk-ins from other
  // staff) current without needing a dedicated SSE channel for what is, so far, a low-traffic screen.
  refreshTimer = setInterval(load, 30000)
})
onUnmounted(() => { if (refreshTimer) clearInterval(refreshTimer) })

function resetForm() {
  Object.assign(form, { guestName: '', guestPhone: '', guestEmail: '', partySize: 2, quotedMinutes: null, notes: '' })
  formError.value = ''
}

async function submit() {
  if (!admin.restaurantId || creating.value) return
  creating.value = true
  formError.value = ''
  try {
    await addToWaitlist(admin.restaurantId, {
      guest_name: form.guestName.trim(), guest_phone: form.guestPhone.trim() || undefined,
      guest_email: form.guestEmail.trim() || undefined, party_size: form.partySize,
      quoted_minutes: form.quotedMinutes ?? undefined, notes: form.notes.trim() || undefined,
    })
    resetForm()
    showForm.value = false
    await load()
  }
  catch (err) {
    formError.value = err instanceof Error ? err.message : 'Could not add them to the waitlist'
  }
  finally {
    creating.value = false
  }
}

async function notify(entry: WaitlistEntry) {
  if (!admin.restaurantId || busyId.value) return
  busyId.value = entry.id
  try {
    await notifyWaitlistEntry(admin.restaurantId, entry.id)
    ui.success(entry.guest_email ? `Emailed ${entry.guest_name}` : `Marked ${entry.guest_name} as notified`)
    await load()
  }
  catch (err) {
    ui.error(err instanceof Error ? err.message : 'Could not notify them')
  }
  finally {
    busyId.value = null
  }
}

function startSeating(entry: WaitlistEntry) {
  seatingId.value = entry.id
  const fit = tables.value.find(t => t.status === 'AVAILABLE' && t.capacity >= entry.party_size)
  seatTableId.value = fit?.id ?? null
}

async function confirmSeat(entry: WaitlistEntry) {
  if (!admin.restaurantId || !seatTableId.value || busyId.value) return
  busyId.value = entry.id
  try {
    await seatWaitlistEntry(admin.restaurantId, entry.id, seatTableId.value)
    ui.success(`${entry.guest_name} seated`)
    seatingId.value = null
    await load()
  }
  catch (err) {
    ui.error(err instanceof Error ? err.message : 'Could not seat them')
  }
  finally {
    busyId.value = null
  }
}

async function cancel(entry: WaitlistEntry) {
  if (!admin.restaurantId || busyId.value) return
  busyId.value = entry.id
  try {
    await cancelWaitlistEntry(admin.restaurantId, entry.id)
    await load()
  }
  catch (err) {
    ui.error(err instanceof Error ? err.message : 'Could not remove them')
  }
  finally {
    busyId.value = null
  }
}

function availableTablesFor(entry: WaitlistEntry) {
  return tables.value.filter(t => t.status === 'AVAILABLE' && t.capacity >= entry.party_size)
}
</script>

<template>
  <div>
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="font-display text-2xl font-semibold text-brand-900">Waitlist</h1>
        <p class="text-sm text-ink-muted">Walk-ins waiting for a table</p>
      </div>
      <AppButton @click="showForm = !showForm">{{ showForm ? 'Close' : 'Add to waitlist' }}</AppButton>
    </div>

    <form v-if="showForm" class="mt-4 grid gap-3 rounded-2xl border border-brand-100 bg-surface-elevated p-5 sm:grid-cols-2" @submit.prevent="submit">
      <label class="block text-sm font-medium">Name
        <input v-model="form.guestName" required class="mt-1 w-full rounded-lg border px-3 py-2 text-sm" placeholder="Sam">
      </label>
      <label class="block text-sm font-medium">Party size
        <input v-model.number="form.partySize" type="number" min="1" max="20" required class="mt-1 w-full rounded-lg border px-3 py-2 text-sm">
      </label>
      <label class="block text-sm font-medium">Phone <span class="font-normal text-ink-subtle">(optional)</span>
        <input v-model="form.guestPhone" class="mt-1 w-full rounded-lg border px-3 py-2 text-sm" placeholder="555-0100">
      </label>
      <label class="block text-sm font-medium">Email <span class="font-normal text-ink-subtle">(optional — needed to notify by email)</span>
        <input v-model="form.guestEmail" type="email" class="mt-1 w-full rounded-lg border px-3 py-2 text-sm" placeholder="sam@example.com">
      </label>
      <label class="block text-sm font-medium">Quoted wait (minutes) <span class="font-normal text-ink-subtle">(optional)</span>
        <input v-model.number="form.quotedMinutes" type="number" min="0" max="240" class="mt-1 w-full rounded-lg border px-3 py-2 text-sm" placeholder="20">
      </label>
      <label class="block text-sm font-medium sm:col-span-2">Notes <span class="font-normal text-ink-subtle">(optional)</span>
        <input v-model="form.notes" class="mt-1 w-full rounded-lg border px-3 py-2 text-sm" placeholder="High chair needed">
      </label>
      <p v-if="formError" class="text-sm text-red-600 sm:col-span-2" role="alert">{{ formError }}</p>
      <div class="sm:col-span-2">
        <AppButton type="submit" :disabled="creating">{{ creating ? 'Adding…' : 'Add to waitlist' }}</AppButton>
      </div>
    </form>

    <div v-if="loading" class="mt-6 h-40 animate-pulse rounded-2xl bg-brand-100/60" />

    <p v-else-if="!entries.length" class="mt-8 text-sm text-ink-subtle">No one is waiting right now.</p>

    <ul v-else class="mt-6 space-y-3">
      <li v-for="(entry, i) in entries" :key="entry.id" class="rounded-2xl border border-brand-100 bg-surface-elevated p-4">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p class="font-semibold text-ink">
              <span class="mr-2 inline-flex h-6 w-6 items-center justify-center rounded-full bg-brand-100 text-xs font-bold text-brand-800">{{ i + 1 }}</span>
              {{ entry.guest_name }} · party of {{ entry.party_size }}
            </p>
            <p class="mt-1 text-xs text-ink-subtle">
              Waiting {{ entry.waiting_minutes }} min<span v-if="entry.quoted_minutes"> · quoted {{ entry.quoted_minutes }} min</span>
              <span v-if="entry.guest_phone"> · {{ entry.guest_phone }}</span>
              <span v-if="entry.guest_email"> · {{ entry.guest_email }}</span>
            </p>
            <p v-if="entry.notes" class="mt-1 text-xs text-ink-subtle">{{ entry.notes }}</p>
            <span
              v-if="entry.status === 'NOTIFIED'"
              class="mt-2 inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-semibold text-emerald-900"
            >Notified — table ready</span>
          </div>
          <div class="flex flex-wrap items-center gap-2">
            <button
              v-if="entry.status === 'WAITING'"
              type="button" class="rounded-lg border border-brand-200 px-3 py-1.5 text-sm font-medium hover:bg-brand-50"
              :disabled="busyId === entry.id" @click="notify(entry)"
            >
              {{ entry.guest_email ? 'Notify (email)' : 'Mark notified' }}
            </button>
            <button
              type="button" class="rounded-lg bg-brand-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-800"
              :disabled="busyId === entry.id || !availableTablesFor(entry).length" @click="startSeating(entry)"
            >
              Seat
            </button>
            <button
              type="button" class="text-sm font-medium text-red-600 hover:underline"
              :disabled="busyId === entry.id" @click="cancel(entry)"
            >
              Remove
            </button>
          </div>
        </div>

        <div v-if="seatingId === entry.id" class="mt-3 flex flex-wrap items-center gap-2 border-t border-brand-100 pt-3">
          <label class="text-sm font-medium">Table
            <select v-model.number="seatTableId" class="ml-2 rounded-lg border px-2 py-1.5 text-sm">
              <option v-for="t in availableTablesFor(entry)" :key="t.id" :value="t.id">{{ t.table_number }} (seats {{ t.capacity }})</option>
            </select>
          </label>
          <button
            type="button" class="rounded-lg bg-brand-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-800"
            :disabled="!seatTableId || busyId === entry.id" @click="confirmSeat(entry)"
          >
            Confirm seat
          </button>
          <button type="button" class="text-sm text-ink-subtle hover:underline" @click="seatingId = null">Cancel</button>
        </div>
        <p v-else-if="!availableTablesFor(entry).length" class="mt-2 text-xs text-ink-subtle">No free table big enough yet.</p>
      </li>
    </ul>
  </div>
</template>
