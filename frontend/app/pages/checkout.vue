<script setup lang="ts">
import type { OrderType } from '~/types/order'
import type { Reservation } from '~/types/reservation'
import { createOrder } from '~/services/orders'
import { fetchMyReservations } from '~/services/reservations'
import { formatCurrency } from '~/utils/format'

definePageMeta({ middleware: ['auth'] })

const auth = useAuthStore()
const cart = useCartStore()
const restaurant = useRestaurantStore()
const router = useRouter()

if (cart.isEmpty) {
  await navigateTo('/cart')
}

await restaurant.load()

const orderType = ref<OrderType>('PICKUP')
const reservations = ref<Reservation[]>([])
const reservationId = ref<number | undefined>()
const error = ref('')
const submitting = ref(false)

const form = reactive({
  customer_name: auth.user?.first_name ? `${auth.user.first_name} ${auth.user.last_name}` : '',
  customer_email: auth.user?.email || '',
  customer_phone: auth.user?.phone || '',
  street: '',
  city: restaurant.current?.city || '',
  postal_code: restaurant.current?.postal_code || '',
  delivery_instructions: '',
  notes: '',
})

async function loadReservations() {
  if (!restaurant.current) return
  try {
    const all = await fetchMyReservations(restaurant.current.id)
    reservations.value = all.filter(r => r.status === 'CONFIRMED' || r.status === 'HELD' || r.status === 'SEATED')
    if (reservations.value.length && !reservationId.value) {
      reservationId.value = reservations.value[0]?.id
    }
  }
  catch {
    reservations.value = []
  }
}

watch(orderType, async (type) => {
  if (type === 'DINE_IN') await loadReservations()
})

onMounted(async () => {
  if (orderType.value === 'DINE_IN') await loadReservations()
})

const totals = computed(() => {
  if (!restaurant.current) return null
  return cart.computeTotals(restaurant.current, orderType.value)
})

function formatWhen(iso: string) {
  return new Date(iso).toLocaleString(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

async function submitOrder() {
  if (!restaurant.current || !totals.value) return
  error.value = ''
  if (orderType.value === 'DINE_IN' && !reservationId.value) {
    error.value = 'Select a reservation, or book a table first. Walk-ins are seated by staff.'
    return
  }
  submitting.value = true
  try {
    const order = await createOrder({
      restaurant_id: restaurant.current.id,
      order_type: orderType.value,
      items: cart.toOrderItems(),
      customer_name: form.customer_name,
      customer_email: form.customer_email,
      customer_phone: form.customer_phone || undefined,
      reservation_id: orderType.value === 'DINE_IN' ? reservationId.value : undefined,
      delivery_address: orderType.value === 'DELIVERY'
        ? {
            street: form.street,
            city: form.city,
            postal_code: form.postal_code,
            delivery_instructions: form.delivery_instructions || undefined,
          }
        : undefined,
      delivery_instructions: form.delivery_instructions || undefined,
      notes: form.notes || undefined,
    })
    cart.clear()
    await router.push(`/orders/${order.id}`)
  }
  catch (err) {
    error.value = err instanceof Error ? err.message : 'Checkout failed'
  }
  finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="mx-auto max-w-3xl px-4 py-8 sm:px-6">
    <h1 class="font-display text-3xl font-semibold text-brand-900">Checkout</h1>

    <div class="mt-6 grid gap-8 lg:grid-cols-5">
      <div class="space-y-6 lg:col-span-3">
        <section class="rounded-2xl border border-brand-100 bg-surface-elevated p-5">
          <h2 class="font-semibold text-ink">Order type</h2>
          <div class="mt-3 flex flex-wrap gap-2">
            <button
              v-for="type in (['PICKUP', 'DELIVERY', 'DINE_IN'] as OrderType[])"
              :key="type"
              class="rounded-lg px-3 py-2 text-sm font-medium"
              :class="orderType === type ? 'bg-brand-700 text-white' : 'bg-brand-100 text-brand-800'"
              @click="orderType = type"
            >
              {{ type.replace('_', ' ') }}
            </button>
          </div>
        </section>

        <section class="rounded-2xl border border-brand-100 bg-surface-elevated p-5">
          <h2 class="font-semibold text-ink">Contact</h2>
          <div class="mt-3 grid gap-3 sm:grid-cols-2">
            <input v-model="form.customer_name" required placeholder="Name" class="rounded-lg border border-brand-200 px-3 py-2 text-sm sm:col-span-2">
            <input v-model="form.customer_email" required type="email" placeholder="Email" class="rounded-lg border border-brand-200 px-3 py-2 text-sm sm:col-span-2">
            <input v-model="form.customer_phone" placeholder="Phone" class="rounded-lg border border-brand-200 px-3 py-2 text-sm sm:col-span-2">
          </div>
        </section>

        <section v-if="orderType === 'DELIVERY'" class="rounded-2xl border border-brand-100 bg-surface-elevated p-5">
          <h2 class="font-semibold text-ink">Delivery address</h2>
          <div class="mt-3 grid gap-3">
            <input v-model="form.street" required placeholder="Street" class="rounded-lg border border-brand-200 px-3 py-2 text-sm">
            <div class="grid gap-3 sm:grid-cols-2">
              <input v-model="form.city" required placeholder="City" class="rounded-lg border border-brand-200 px-3 py-2 text-sm">
              <input v-model="form.postal_code" required placeholder="Postal code" class="rounded-lg border border-brand-200 px-3 py-2 text-sm">
            </div>
            <input v-model="form.delivery_instructions" placeholder="Delivery instructions" class="rounded-lg border border-brand-200 px-3 py-2 text-sm">
          </div>
        </section>

        <section v-if="orderType === 'DINE_IN'" class="rounded-2xl border border-brand-100 bg-surface-elevated p-5">
          <h2 class="font-semibold text-ink">Reservation</h2>
          <p class="mt-1 text-sm text-ink-muted">
            Dine-in orders need a booked table. Walk-ins are seated by staff at the restaurant.
          </p>
          <div v-if="reservations.length" class="mt-3">
            <select v-model.number="reservationId" required class="w-full rounded-lg border border-brand-200 px-3 py-2 text-sm">
              <option v-for="r in reservations" :key="r.id" :value="r.id">
                Table {{ r.table_number }} · {{ formatWhen(r.starts_at) }} · {{ r.party_size }} guests ({{ r.status }})
              </option>
            </select>
          </div>
          <div v-else class="mt-3 rounded-lg bg-brand-50 px-3 py-3 text-sm text-brand-900">
            No active reservations found.
            <NuxtLink to="/reserve" class="font-medium underline">Book a table</NuxtLink>
            first, then return to checkout.
          </div>
        </section>

        <section class="rounded-2xl border border-brand-100 bg-surface-elevated p-5">
          <h2 class="font-semibold text-ink">Payment</h2>
          <p class="mt-2 text-sm text-ink-muted">Mock payment — no card required for this demo.</p>
        </section>
      </div>

      <aside class="lg:col-span-2">
        <div class="sticky top-6 rounded-2xl border border-brand-100 bg-surface-elevated p-5">
          <h2 class="font-semibold text-ink">Order summary</h2>
          <ul class="mt-4 space-y-2 text-sm">
            <li v-for="line in cart.lines" :key="line.id" class="flex justify-between gap-2">
              <span>{{ line.quantity }}× {{ line.name }}</span>
              <span>{{ formatCurrency(line.unit_price * line.quantity) }}</span>
            </li>
          </ul>
          <div v-if="totals" class="mt-4 space-y-1 border-t border-brand-100 pt-4 text-sm">
            <div class="flex justify-between"><span>Subtotal</span><span>{{ formatCurrency(totals.subtotal) }}</span></div>
            <div class="flex justify-between"><span>Tax</span><span>{{ formatCurrency(totals.tax) }}</span></div>
            <div v-if="totals.delivery_fee" class="flex justify-between"><span>Delivery</span><span>{{ formatCurrency(totals.delivery_fee) }}</span></div>
            <div class="flex justify-between font-semibold text-brand-900"><span>Total</span><span>{{ formatCurrency(totals.total) }}</span></div>
          </div>
          <p v-if="error" class="mt-4 text-sm text-red-600">{{ error }}</p>
          <AppButton class="mt-4 w-full" :disabled="submitting" @click="submitOrder">
            {{ submitting ? 'Placing order…' : 'Place order' }}
          </AppButton>
        </div>
      </aside>
    </div>
  </div>
</template>
