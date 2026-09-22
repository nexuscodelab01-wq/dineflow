<script setup lang="ts">
import type { Reservation } from '~/types/reservation'
import { cancelReservationByActionToken, confirmReservationByActionToken, fetchReservationByActionToken } from '~/services/reservations'
import { ApiError } from '~/utils/api-error'
import { formatWhen } from '~/utils/datetime'

// A guest lands here straight from an email link — no account, the token itself proves the booking is theirs.
const route = useRoute()
const branding = useBranding()
const token = computed(() => (typeof route.query.token === 'string' ? route.query.token : ''))

const reservation = ref<Reservation | null>(null)
const loading = ref(true)
const error = ref('')
const confirming = ref(false)
const cancelling = ref(false)
const cancelled = ref(false)

async function load() {
  if (!token.value) {
    loading.value = false
    return
  }
  loading.value = true
  error.value = ''
  try {
    reservation.value = await fetchReservationByActionToken(token.value)
  }
  catch (err) {
    error.value = err instanceof ApiError ? err.message : 'Something went wrong. Please try again.'
  }
  finally {
    loading.value = false
  }
}

onMounted(load)

const canAct = computed(() => reservation.value && ['HELD', 'CONFIRMED', 'SEATED'].includes(reservation.value.status))

async function confirmAttendance() {
  if (!token.value || confirming.value) return
  confirming.value = true
  error.value = ''
  try {
    reservation.value = await confirmReservationByActionToken(token.value)
  }
  catch (err) {
    error.value = err instanceof ApiError ? err.message : 'Could not confirm. Please try again.'
  }
  finally {
    confirming.value = false
  }
}

async function cancelBooking() {
  if (!token.value || cancelling.value) return
  if (!window.confirm('Cancel this reservation? This cannot be undone from here.')) return
  cancelling.value = true
  error.value = ''
  try {
    reservation.value = await cancelReservationByActionToken(token.value)
    cancelled.value = true
  }
  catch (err) {
    error.value = err instanceof ApiError ? err.message : 'Could not cancel. Please try again.'
  }
  finally {
    cancelling.value = false
  }
}
</script>

<template>
  <div class="mx-auto flex min-h-[70vh] max-w-md flex-col justify-center px-4 py-12 sm:px-6">
    <div class="rounded-2xl border border-brand-100 bg-surface-elevated p-8 shadow-sm">
      <h1 class="font-display text-2xl font-semibold text-brand-900">
        {{ branding.name.value ? `Your reservation at ${branding.name.value}` : 'Your reservation' }}
      </h1>

      <div v-if="!token" class="mt-6">
        <p class="text-ink">This page needs the link from your email.</p>
      </div>

      <div v-else-if="loading" class="mt-6 h-24 animate-pulse rounded-xl bg-brand-100/60" />

      <div v-else-if="error && !reservation" class="mt-6 space-y-2">
        <p class="text-sm text-red-600" role="alert">{{ error }}</p>
        <p class="text-sm text-ink-muted">If this link has expired, please contact the restaurant directly.</p>
      </div>

      <div v-else-if="reservation" class="mt-6 space-y-4">
        <div class="rounded-xl bg-surface-muted/60 p-4">
          <p class="text-lg font-semibold text-ink">{{ formatWhen(reservation.starts_at) }}</p>
          <p class="mt-1 text-sm text-ink-muted">
            Party of {{ reservation.party_size }}<span v-if="reservation.table_number"> · Table {{ reservation.table_number }}</span>
          </p>
          <StatusBadge class="mt-2" :status="reservation.status" />
        </div>

        <p v-if="cancelled" class="rounded-lg bg-red-50 px-3 py-2 text-sm font-medium text-red-800" role="status">
          Your reservation has been cancelled. We'd love to see you another time.
        </p>
        <p v-else-if="reservation.guest_confirmed_at" class="rounded-lg bg-emerald-50 px-3 py-2 text-sm font-medium text-emerald-800" role="status">
          Thanks — we've let the restaurant know you're coming!
        </p>

        <p v-if="error" class="text-sm text-red-600" role="alert">{{ error }}</p>

        <div v-if="canAct && !cancelled" class="flex flex-col gap-2 sm:flex-row">
          <AppButton class="flex-1" :disabled="confirming || !!reservation.guest_confirmed_at" @click="confirmAttendance">
            {{ reservation.guest_confirmed_at ? "You're confirmed" : confirming ? 'Confirming…' : "I'll be there" }}
          </AppButton>
          <button
            class="flex-1 rounded-lg border border-red-200 px-4 py-2 text-sm font-semibold text-red-700 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50"
            :disabled="cancelling"
            @click="cancelBooking"
          >
            {{ cancelling ? 'Cancelling…' : 'Cancel reservation' }}
          </button>
        </div>
        <p v-else-if="!cancelled" class="text-sm text-ink-muted">This booking can no longer be changed here. Please contact the restaurant.</p>
      </div>
    </div>
  </div>
</template>
