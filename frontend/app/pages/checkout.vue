<script setup lang="ts">
import type { OrderType } from '~/types/order'
import type { Reservation } from '~/types/reservation'
import type { PickupSlot } from '~/types/scheduling'
import { createOrder } from '~/services/orders'
import { previewCoupon } from '~/services/coupons'
import { fetchPickupSlots } from '~/services/scheduling'
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

// Ordering ahead: the slot list comes from the server (built from the restaurant's opening hours in
// its own timezone), and the chosen slot is re-checked there when the order goes in.
const scheduledOrdersEnabled = useFeature('scheduled_orders')
const WHEN_MODES = [
  { value: 'asap', label: 'As soon as possible' },
  { value: 'later', label: 'Order ahead' },
] as const
const whenMode = ref<'asap' | 'later'>('asap')
const slotDate = ref('')
const slots = ref<PickupSlot[]>([])
const chosenSlot = ref('')
const slotTimezone = ref('')
const loadingSlots = ref(false)
const slotError = ref('')
const slotDays = ref<{ value: string, label: string }[]>([])

// Dine-in is served at the booking time, so ordering ahead only applies to pickup and delivery.
const canScheduleThisOrder = computed(() => scheduledOrdersEnabled.value && orderType.value !== 'DINE_IN')

function formatSlot(iso: string) {
  return new Date(iso).toLocaleTimeString(undefined, {
    hour: 'numeric', minute: '2-digit', timeZone: slotTimezone.value || undefined,
  })
}

async function loadSlots() {
  if (!restaurant.current || !slotDate.value) return
  loadingSlots.value = true
  slotError.value = ''
  try {
    const result = await fetchPickupSlots(restaurant.current.slug, slotDate.value)
    slots.value = result.slots
    slotTimezone.value = result.timezone
    if (!result.slots.some(s => s.at === chosenSlot.value)) chosenSlot.value = ''
    if (!slotDays.value.length) {
      // Offer today plus however many days ahead this restaurant accepts.
      const start = new Date(`${result.date}T00:00:00`)
      slotDays.value = Array.from({ length: result.days_ahead + 1 }, (_, i) => {
        const day = new Date(start)
        day.setDate(day.getDate() + i)
        const value = day.toISOString().slice(0, 10)
        const label = i === 0 ? 'Today' : i === 1 ? 'Tomorrow' : day.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })
        return { value, label }
      })
    }
  }
  catch (err) {
    slots.value = []
    slotError.value = err instanceof Error ? err.message : 'Could not load collection times'
  }
  finally {
    loadingSlots.value = false
  }
}

watch(whenMode, async (mode) => {
  if (mode !== 'later') {
    chosenSlot.value = ''
    return
  }
  if (!slotDate.value) slotDate.value = new Date().toISOString().slice(0, 10)
  await loadSlots()
})
watch(slotDate, loadSlots)
// Switching to dine-in makes a slot meaningless — drop back to "as soon as possible".
watch(orderType, (type) => {
  if (type === 'DINE_IN') whenMode.value = 'asap'
})

// Coupons: the code is checked here only so the customer can see what it's worth before paying.
// The order endpoint works the discount out again from its own subtotal, so this is never the
// number that's charged.
const couponsEnabled = useFeature('coupons')
const couponCode = ref('')
const appliedCoupon = ref<{ code: string, discount: number } | null>(null)
const couponError = ref('')
const checkingCoupon = ref(false)

const totals = computed(() => {
  if (!restaurant.current) return null
  return cart.computeTotals(restaurant.current, orderType.value, appliedCoupon.value?.discount ?? 0)
})

async function applyCoupon() {
  const code = couponCode.value.trim()
  if (!code || checkingCoupon.value || !totals.value) return
  checkingCoupon.value = true
  couponError.value = ''
  try {
    const preview = await previewCoupon(code, totals.value.subtotal)
    appliedCoupon.value = { code: preview.code, discount: Number(preview.discount) }
    couponCode.value = ''
  }
  catch (err) {
    appliedCoupon.value = null
    couponError.value = err instanceof Error ? err.message : "That code isn't valid here"
  }
  finally {
    checkingCoupon.value = false
  }
}

function removeCoupon() {
  appliedCoupon.value = null
  couponError.value = ''
}

// A cart edit in another tab can change the subtotal out from under a minimum-spend coupon, so
// re-check it rather than showing a discount the server would then refuse.
watch(() => totals.value?.subtotal, async (subtotal, previous) => {
  if (!appliedCoupon.value || subtotal === previous || subtotal === undefined) return
  try {
    const preview = await previewCoupon(appliedCoupon.value.code, subtotal)
    appliedCoupon.value = { code: preview.code, discount: Number(preview.discount) }
  }
  catch (err) {
    couponError.value = err instanceof Error ? err.message : 'That code no longer applies'
    appliedCoupon.value = null
  }
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
  if (whenMode.value === 'later' && !chosenSlot.value) {
    error.value = 'Pick a collection time, or switch back to as soon as possible.'
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
      coupon_code: appliedCoupon.value?.code,
      scheduled_for: whenMode.value === 'later' ? chosenSlot.value : undefined,
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

        <section v-if="canScheduleThisOrder" class="rounded-2xl border border-brand-100 bg-surface-elevated p-5">
          <h2 class="font-semibold text-ink">When</h2>
          <div class="mt-3 flex flex-wrap gap-2">
            <button
              v-for="mode in WHEN_MODES" :key="mode.value" type="button"
              class="rounded-lg px-3 py-2 text-sm font-medium"
              :class="whenMode === mode.value ? 'bg-brand-700 text-white' : 'bg-brand-100 text-brand-800'"
              @click="whenMode = mode.value"
            >
              {{ mode.label }}
            </button>
          </div>

          <div v-if="whenMode === 'later'" class="mt-4 space-y-3">
            <label class="block text-sm font-medium">Day
              <select v-model="slotDate" class="mt-1 w-full rounded-lg border border-brand-200 px-3 py-2 text-sm">
                <option v-for="day in slotDays" :key="day.value" :value="day.value">{{ day.label }}</option>
              </select>
            </label>

            <div v-if="loadingSlots" class="h-10 animate-pulse rounded-lg bg-brand-100/60" />
            <p v-else-if="slotError" class="text-sm text-red-600">{{ slotError }}</p>
            <p v-else-if="!slots.length" class="text-sm text-ink-subtle">No collection times left that day. Try another.</p>
            <div v-else>
              <p class="text-sm font-medium">Collection time</p>
              <div class="mt-2 flex flex-wrap gap-2">
                <button
                  v-for="slot in slots" :key="slot.at" type="button"
                  class="rounded-lg px-3 py-1.5 text-sm font-medium"
                  :class="chosenSlot === slot.at ? 'bg-brand-700 text-white' : 'border border-brand-200 hover:bg-brand-50'"
                  @click="chosenSlot = slot.at"
                >
                  {{ formatSlot(slot.at) }}
                </button>
              </div>
              <p v-if="slotTimezone" class="mt-2 text-xs text-ink-subtle">Times shown in {{ slotTimezone }}</p>
            </div>
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
          <div v-if="couponsEnabled" class="mt-4 border-t border-brand-100 pt-4">
            <div v-if="appliedCoupon" class="flex items-center justify-between gap-2 rounded-lg bg-brand-50 px-3 py-2 text-sm">
              <span class="font-semibold text-brand-800">{{ appliedCoupon.code }} applied</span>
              <button type="button" class="text-xs font-medium text-ink-subtle hover:underline" @click="removeCoupon">Remove</button>
            </div>
            <form v-else class="flex gap-2" @submit.prevent="applyCoupon">
              <input
                v-model="couponCode" type="text" placeholder="Discount code" autocomplete="off"
                class="min-w-0 flex-1 rounded-lg border border-brand-200 px-3 py-2 text-sm uppercase placeholder:normal-case"
              >
              <button
                type="submit" class="shrink-0 rounded-lg border border-brand-200 px-3 py-2 text-sm font-medium hover:bg-brand-50 disabled:opacity-50"
                :disabled="!couponCode.trim() || checkingCoupon"
              >
                {{ checkingCoupon ? 'Checking…' : 'Apply' }}
              </button>
            </form>
            <p v-if="couponError" class="mt-2 text-xs text-red-600" role="alert">{{ couponError }}</p>
          </div>

          <div v-if="totals" class="mt-4 space-y-1 border-t border-brand-100 pt-4 text-sm">
            <div class="flex justify-between"><span>Subtotal</span><span>{{ formatCurrency(totals.subtotal) }}</span></div>
            <div v-if="totals.discount" class="flex justify-between text-emerald-700">
              <span>Discount</span><span>−{{ formatCurrency(totals.discount) }}</span>
            </div>
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
