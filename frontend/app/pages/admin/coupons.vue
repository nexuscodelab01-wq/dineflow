<script setup lang="ts">
import type { Coupon, CouponDiscountType } from '~/types/coupon'
import { createCoupon, deleteCoupon, fetchCoupons, updateCoupon } from '~/services/coupons'

definePageMeta({ layout: 'admin', middleware: ['staff'] })

const admin = useAdminStore()
const auth = useAuthStore()
const ui = useUiStore()

const coupons = ref<Coupon[]>([])
const loading = ref(true)
const showForm = ref(false)
const creating = ref(false)
const formError = ref('')
const busyId = ref<number | null>(null)

const form = reactive({
  code: '',
  description: '',
  discount_type: 'PERCENT' as CouponDiscountType,
  discount_value: '',
  min_order_amount: '',
  max_discount_amount: '',
  ends_at: '',
  max_redemptions: null as number | null,
  max_per_customer: null as number | null,
})

async function load() {
  if (!admin.restaurantId) return
  coupons.value = await fetchCoupons(admin.restaurantId)
}

onMounted(async () => {
  await admin.initialize()
  await load()
  loading.value = false
})

function resetForm() {
  Object.assign(form, {
    code: '', description: '', discount_type: 'PERCENT', discount_value: '', min_order_amount: '',
    max_discount_amount: '', ends_at: '', max_redemptions: null, max_per_customer: null,
  })
  formError.value = ''
}

async function submit() {
  if (!admin.restaurantId || creating.value) return
  creating.value = true
  formError.value = ''
  try {
    await createCoupon(admin.restaurantId, {
      code: form.code.trim(),
      description: form.description.trim() || undefined,
      discount_type: form.discount_type,
      discount_value: form.discount_value,
      min_order_amount: form.min_order_amount || undefined,
      max_discount_amount: form.discount_type === 'PERCENT' && form.max_discount_amount ? form.max_discount_amount : undefined,
      // A date input gives a plain day; treat it as the end of that day in the browser's zone.
      ends_at: form.ends_at ? new Date(`${form.ends_at}T23:59:59`).toISOString() : undefined,
      max_redemptions: form.max_redemptions ?? undefined,
      max_per_customer: form.max_per_customer ?? undefined,
    })
    resetForm()
    showForm.value = false
    await load()
  }
  catch (err) {
    formError.value = err instanceof Error ? err.message : 'Could not create that coupon'
  }
  finally {
    creating.value = false
  }
}

async function toggleActive(coupon: Coupon) {
  if (!admin.restaurantId || busyId.value) return
  busyId.value = coupon.id
  try {
    const updated = await updateCoupon(admin.restaurantId, coupon.id, { is_active: !coupon.is_active })
    const i = coupons.value.findIndex(c => c.id === coupon.id)
    if (i !== -1) coupons.value[i] = updated
  }
  catch (err) {
    ui.error(err instanceof Error ? err.message : 'Could not update that coupon')
  }
  finally {
    busyId.value = null
  }
}

async function remove(coupon: Coupon) {
  if (!admin.restaurantId || busyId.value) return
  busyId.value = coupon.id
  try {
    await deleteCoupon(admin.restaurantId, coupon.id)
    await load()
  }
  catch (err) {
    ui.error(err instanceof Error ? err.message : 'Could not remove that coupon')
  }
  finally {
    busyId.value = null
  }
}

function valueLabel(coupon: Coupon) {
  return coupon.discount_type === 'PERCENT'
    ? `${Number(coupon.discount_value)}% off`
    : `${Number(coupon.discount_value).toFixed(2)} off`
}

function limitLabel(coupon: Coupon) {
  const parts: string[] = []
  if (coupon.min_order_amount) parts.push(`min ${Number(coupon.min_order_amount).toFixed(2)}`)
  if (coupon.max_discount_amount) parts.push(`max ${Number(coupon.max_discount_amount).toFixed(2)} off`)
  if (coupon.max_redemptions) parts.push(`${coupon.times_redeemed}/${coupon.max_redemptions} claimed`)
  else parts.push(`${coupon.times_redeemed} claimed`)
  if (coupon.max_per_customer) parts.push(`${coupon.max_per_customer} per customer`)
  if (coupon.ends_at) parts.push(`until ${new Date(coupon.ends_at).toLocaleDateString()}`)
  return parts.join(' · ')
}

function isExpired(coupon: Coupon) {
  return Boolean(coupon.ends_at && new Date(coupon.ends_at) < new Date())
}
</script>

<template>
  <div>
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="font-display text-2xl font-semibold text-brand-900">Discount codes</h1>
        <p class="text-sm text-ink-muted">Codes customers can enter at checkout</p>
      </div>
      <AppButton v-if="auth.isAdmin" @click="showForm = !showForm">{{ showForm ? 'Close' : 'New code' }}</AppButton>
    </div>

    <form v-if="showForm" class="mt-4 grid gap-3 rounded-2xl border border-brand-100 bg-surface-elevated p-5 sm:grid-cols-2" @submit.prevent="submit">
      <label class="block text-sm font-medium">Code
        <input v-model="form.code" required maxlength="40" class="mt-1 w-full rounded-lg border px-3 py-2 text-sm uppercase" placeholder="SAVE10">
      </label>
      <label class="block text-sm font-medium">Description <span class="font-normal text-ink-subtle">(optional)</span>
        <input v-model="form.description" maxlength="200" class="mt-1 w-full rounded-lg border px-3 py-2 text-sm" placeholder="10% off your order">
      </label>
      <label class="block text-sm font-medium">Type
        <select v-model="form.discount_type" class="mt-1 w-full rounded-lg border px-3 py-2 text-sm">
          <option value="PERCENT">Percentage off</option>
          <option value="FIXED">Amount off</option>
        </select>
      </label>
      <label class="block text-sm font-medium">{{ form.discount_type === 'PERCENT' ? 'Percent' : 'Amount' }}
        <input v-model="form.discount_value" type="number" step="0.01" min="0.01" :max="form.discount_type === 'PERCENT' ? 100 : undefined" required class="mt-1 w-full rounded-lg border px-3 py-2 text-sm">
      </label>
      <label class="block text-sm font-medium">Minimum order <span class="font-normal text-ink-subtle">(optional)</span>
        <input v-model="form.min_order_amount" type="number" step="0.01" min="0" class="mt-1 w-full rounded-lg border px-3 py-2 text-sm" placeholder="—">
      </label>
      <label v-if="form.discount_type === 'PERCENT'" class="block text-sm font-medium">Most it can take off <span class="font-normal text-ink-subtle">(optional)</span>
        <input v-model="form.max_discount_amount" type="number" step="0.01" min="0.01" class="mt-1 w-full rounded-lg border px-3 py-2 text-sm" placeholder="—">
      </label>
      <label class="block text-sm font-medium">Total uses <span class="font-normal text-ink-subtle">(optional)</span>
        <input v-model.number="form.max_redemptions" type="number" min="1" class="mt-1 w-full rounded-lg border px-3 py-2 text-sm" placeholder="Unlimited">
      </label>
      <label class="block text-sm font-medium">Uses per customer <span class="font-normal text-ink-subtle">(optional)</span>
        <input v-model.number="form.max_per_customer" type="number" min="1" class="mt-1 w-full rounded-lg border px-3 py-2 text-sm" placeholder="Unlimited">
      </label>
      <label class="block text-sm font-medium">Last day <span class="font-normal text-ink-subtle">(optional)</span>
        <input v-model="form.ends_at" type="date" class="mt-1 w-full rounded-lg border px-3 py-2 text-sm">
      </label>
      <p v-if="formError" class="text-sm text-red-600 sm:col-span-2" role="alert">{{ formError }}</p>
      <div class="sm:col-span-2">
        <AppButton type="submit" :disabled="creating">{{ creating ? 'Creating…' : 'Create code' }}</AppButton>
      </div>
    </form>

    <div v-if="loading" class="mt-6 h-40 animate-pulse rounded-2xl bg-brand-100/60" />

    <p v-else-if="!coupons.length" class="mt-8 text-sm text-ink-subtle">No discount codes yet.</p>

    <ul v-else class="mt-6 space-y-3">
      <li v-for="coupon in coupons" :key="coupon.id" class="rounded-2xl border border-brand-100 bg-surface-elevated p-4">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div class="flex flex-wrap items-center gap-2">
              <span class="rounded-md bg-brand-50 px-2 py-0.5 font-mono text-sm font-semibold tracking-wider text-brand-800">{{ coupon.code }}</span>
              <span class="text-sm font-medium text-ink">{{ valueLabel(coupon) }}</span>
              <span v-if="!coupon.is_active" class="rounded-full bg-brand-100 px-2 py-0.5 text-xs font-semibold text-brand-800">Off</span>
              <span v-else-if="isExpired(coupon)" class="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-900">Expired</span>
            </div>
            <p v-if="coupon.description" class="mt-1 text-sm text-ink-muted">{{ coupon.description }}</p>
            <p class="mt-1 text-xs text-ink-subtle">{{ limitLabel(coupon) }}</p>
          </div>
          <div v-if="auth.isAdmin" class="flex flex-wrap items-center gap-2">
            <button
              type="button" class="rounded-lg border border-brand-200 px-3 py-1.5 text-sm font-medium hover:bg-brand-50"
              :disabled="busyId === coupon.id" @click="toggleActive(coupon)"
            >
              {{ coupon.is_active ? 'Turn off' : 'Turn on' }}
            </button>
            <button
              type="button" class="text-sm font-medium text-red-600 hover:underline"
              :disabled="busyId === coupon.id" @click="remove(coupon)"
            >
              {{ coupon.times_redeemed ? 'Retire' : 'Delete' }}
            </button>
          </div>
        </div>
      </li>
    </ul>
  </div>
</template>
