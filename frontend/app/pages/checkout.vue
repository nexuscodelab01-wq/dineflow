<script setup lang="ts">
import type { OrderType } from '~/types/order'
import type { RestaurantTable } from '~/types/menu'
import { createOrder } from '~/services/orders'
import { fetchRestaurantTables } from '~/services/menu'
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
const tables = ref<RestaurantTable[]>([])
const tableId = ref<number | undefined>()
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

watch(orderType, async (type) => {
  if (type === 'DINE_IN' && restaurant.current) {
    tables.value = await fetchRestaurantTables(restaurant.current.slug)
  }
})

onMounted(async () => {
  if (orderType.value === 'DINE_IN' && restaurant.current) {
    tables.value = await fetchRestaurantTables(restaurant.current.slug)
  }
})

const totals = computed(() => {
  if (!restaurant.current) return null
  return cart.computeTotals(restaurant.current, orderType.value)
})

async function submitOrder() {
  if (!restaurant.current || !totals.value) return
  error.value = ''
  submitting.value = true
  try {
    const order = await createOrder({
      restaurant_id: restaurant.current.id,
      order_type: orderType.value,
      items: cart.toOrderItems(),
      customer_name: form.customer_name,
      customer_email: form.customer_email,
      customer_phone: form.customer_phone || undefined,
      table_id: orderType.value === 'DINE_IN' ? tableId.value : undefined,
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
          <h2 class="font-semibold text-ink">Table</h2>
          <select v-model="tableId" required class="mt-3 w-full rounded-lg border border-brand-200 px-3 py-2 text-sm">
            <option :value="undefined" disabled>Select a table</option>
            <option v-for="table in tables" :key="table.id" :value="table.id">
              Table {{ table.table_number }} (seats {{ table.capacity }})
            </option>
          </select>
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
