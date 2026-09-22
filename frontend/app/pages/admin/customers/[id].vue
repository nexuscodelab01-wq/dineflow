<script setup lang="ts">
import type { CustomerDetail } from '~/types/admin'
import { fetchAdminCustomer, updateAdminCustomer } from '~/services/admin'
import { formatCurrency } from '~/utils/format'

definePageMeta({ layout: 'admin', middleware: ['staff'] })

const route = useRoute()
const admin = useAdminStore()
const ui = useUiStore()
const detail = ref<CustomerDetail | null>(null)
const loading = ref(true)

const notes = ref('')
const allergies = ref('')
const isVip = ref(false)
const saving = ref(false)

async function load() {
  await admin.initialize()
  if (admin.restaurantId) {
    detail.value = await fetchAdminCustomer(admin.restaurantId, Number(route.params.id))
    notes.value = detail.value.notes ?? ''
    allergies.value = detail.value.allergies ?? ''
    isVip.value = detail.value.is_vip
  }
  loading.value = false
}

onMounted(load)

async function saveProfile() {
  if (!admin.restaurantId || !detail.value || saving.value) return
  saving.value = true
  try {
    await updateAdminCustomer(admin.restaurantId, detail.value.id, {
      notes: notes.value.trim() || null,
      allergies: allergies.value.trim() || null,
      is_vip: isVip.value,
    })
    detail.value = { ...detail.value, notes: notes.value.trim() || null, allergies: allergies.value.trim() || null, is_vip: isVip.value }
    ui.success('Saved')
  }
  catch (err) {
    ui.error(err instanceof Error ? err.message : 'Could not save')
  }
  finally {
    saving.value = false
  }
}

const reservationStatusLabel: Record<string, string> = {
  HELD: 'Held', CONFIRMED: 'Confirmed', SEATED: 'Seated', COMPLETED: 'Completed', CANCELLED: 'Cancelled', NO_SHOW: 'No-show',
}
</script>

<template>
  <div>
    <NuxtLink to="/admin/customers" class="text-sm font-medium text-brand-700">← Customers</NuxtLink>

    <div v-if="loading" class="mt-6 h-40 animate-pulse rounded-2xl bg-brand-100/60" />

    <div v-else-if="detail" class="mt-6 grid gap-6 lg:grid-cols-[1fr_20rem]">
      <div class="space-y-6">
        <section class="rounded-2xl border border-brand-100 bg-surface-elevated p-6">
          <div class="flex flex-wrap items-center gap-2">
            <h1 class="font-display text-2xl font-semibold">{{ detail.first_name }} {{ detail.last_name }}</h1>
            <span v-if="detail.is_vip" class="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-bold uppercase tracking-wide text-amber-800">VIP</span>
            <span v-if="!detail.is_active" class="rounded-full bg-red-100 px-2 py-0.5 text-xs font-semibold text-red-800">Inactive</span>
          </div>
          <p class="mt-1 text-sm text-ink-muted">{{ detail.email }}<span v-if="detail.phone"> · {{ detail.phone }}</span></p>
          <p class="mt-2 text-sm text-ink-muted">
            {{ detail.total_orders }} order{{ detail.total_orders === 1 ? '' : 's' }} · {{ formatCurrency(Number(detail.total_spending)) }} total ·
            {{ detail.total_bookings }} booking{{ detail.total_bookings === 1 ? '' : 's' }}
          </p>
          <p v-if="detail.allergies" class="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm font-semibold text-red-900">
            ⚠ Allergies: {{ detail.allergies }}
          </p>
        </section>

        <section v-if="detail.orders.length" class="rounded-2xl border border-brand-100 bg-surface-elevated p-6">
          <h2 class="font-semibold">Order history</h2>
          <ul class="mt-4 space-y-3">
            <li v-for="order in detail.orders" :key="order.id" class="flex justify-between text-sm">
              <span>{{ order.order_number }} · {{ new Date(order.created_at).toLocaleDateString() }}</span>
              <span>{{ formatCurrency(Number(order.total)) }}</span>
            </li>
          </ul>
        </section>

        <section v-if="detail.reservations.length" class="rounded-2xl border border-brand-100 bg-surface-elevated p-6">
          <h2 class="font-semibold">Booking history</h2>
          <ul class="mt-4 space-y-3">
            <li v-for="r in detail.reservations" :key="r.id" class="flex justify-between text-sm">
              <span>{{ new Date(r.starts_at).toLocaleString() }} · party of {{ r.party_size }}<span v-if="r.table_number"> · table {{ r.table_number }}</span></span>
              <StatusBadge :status="r.status" />
            </li>
          </ul>
        </section>

        <p v-if="!detail.orders.length && !detail.reservations.length" class="text-sm text-ink-subtle">No orders or bookings yet.</p>
      </div>

      <aside class="h-fit rounded-2xl border border-brand-100 bg-surface-elevated p-6">
        <h2 class="font-semibold">Guest profile</h2>
        <p class="mt-1 text-xs text-ink-subtle">Only your staff can see this — never shown to the guest.</p>
        <label class="mt-4 flex items-center gap-2 text-sm font-medium">
          <input v-model="isVip" type="checkbox"> VIP
        </label>
        <label class="mt-4 block text-sm font-medium">Allergies
          <textarea v-model="allergies" rows="2" maxlength="1000" class="mt-1 w-full rounded-lg border px-3 py-2 text-sm" placeholder="e.g. Shellfish, peanuts" />
        </label>
        <label class="mt-3 block text-sm font-medium">Notes
          <textarea v-model="notes" rows="4" maxlength="4000" class="mt-1 w-full rounded-lg border px-3 py-2 text-sm" placeholder="Preferences, occasions, anything worth remembering" />
        </label>
        <AppButton class="mt-3 w-full" :disabled="saving" @click="saveProfile">{{ saving ? 'Saving…' : 'Save' }}</AppButton>
      </aside>
    </div>
  </div>
</template>
