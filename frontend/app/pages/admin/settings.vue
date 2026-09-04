<script setup lang="ts">
import type { Restaurant } from '~/types/menu'
import { fetchAdminSettings, updateAdminSettings } from '~/services/admin'

definePageMeta({ layout: 'admin', middleware: ['admin'] })

const admin = useAdminStore()
const settings = ref<Restaurant | null>(null)
const loading = ref(true)
const saving = ref(false)
const message = ref('')

const form = reactive({
  name: '',
  description: '',
  phone: '',
  email: '',
  address: '',
  city: '',
  postal_code: '',
  delivery_enabled: true,
  pickup_enabled: true,
  dine_in_enabled: true,
  tax_rate: '',
  delivery_fee: '',
})

onMounted(async () => {
  await admin.initialize()
  if (admin.restaurantId) {
    settings.value = await fetchAdminSettings(admin.restaurantId)
    Object.assign(form, {
      name: settings.value.name,
      description: settings.value.description || '',
      phone: settings.value.phone || '',
      email: settings.value.email || '',
      address: settings.value.address || '',
      city: settings.value.city || '',
      postal_code: settings.value.postal_code || '',
      delivery_enabled: settings.value.delivery_enabled,
      pickup_enabled: settings.value.pickup_enabled,
      dine_in_enabled: settings.value.dine_in_enabled,
      tax_rate: settings.value.tax_rate,
      delivery_fee: settings.value.delivery_fee,
    })
  }
  loading.value = false
})

async function save() {
  if (!admin.restaurantId) return
  saving.value = true
  message.value = ''
  try {
    settings.value = await updateAdminSettings(admin.restaurantId, {
      ...form,
      tax_rate: form.tax_rate,
      delivery_fee: form.delivery_fee,
    })
    message.value = 'Settings saved'
  }
  catch (err) {
    message.value = err instanceof Error ? err.message : 'Save failed'
  }
  finally {
    saving.value = false
  }
}
</script>

<template>
  <div>
    <h1 class="font-display text-2xl font-semibold text-brand-900">Restaurant settings</h1>
    <p class="text-sm text-ink-muted">Profile, ordering options, and fees</p>

    <div v-if="loading" class="mt-6 h-64 animate-pulse rounded-2xl bg-brand-100/60" />

    <form v-else class="mt-6 max-w-2xl space-y-6" @submit.prevent="save">
      <section class="rounded-2xl border border-brand-100 bg-surface-elevated p-6 space-y-3">
        <h2 class="font-semibold">Profile</h2>
        <input v-model="form.name" required class="w-full rounded-lg border px-3 py-2 text-sm" placeholder="Restaurant name">
        <textarea v-model="form.description" rows="3" class="w-full rounded-lg border px-3 py-2 text-sm" placeholder="Description" />
        <div class="grid gap-3 sm:grid-cols-2">
          <input v-model="form.phone" class="rounded-lg border px-3 py-2 text-sm" placeholder="Phone">
          <input v-model="form.email" class="rounded-lg border px-3 py-2 text-sm" placeholder="Email">
        </div>
        <input v-model="form.address" class="w-full rounded-lg border px-3 py-2 text-sm" placeholder="Address">
        <div class="grid gap-3 sm:grid-cols-2">
          <input v-model="form.city" class="rounded-lg border px-3 py-2 text-sm" placeholder="City">
          <input v-model="form.postal_code" class="rounded-lg border px-3 py-2 text-sm" placeholder="Postal code">
        </div>
      </section>

      <section class="rounded-2xl border border-brand-100 bg-surface-elevated p-6 space-y-3">
        <h2 class="font-semibold">Ordering</h2>
        <label class="flex items-center gap-2 text-sm"><input v-model="form.delivery_enabled" type="checkbox"> Delivery enabled</label>
        <label class="flex items-center gap-2 text-sm"><input v-model="form.pickup_enabled" type="checkbox"> Pickup enabled</label>
        <label class="flex items-center gap-2 text-sm"><input v-model="form.dine_in_enabled" type="checkbox"> Dine-in enabled</label>
        <div class="grid gap-3 sm:grid-cols-2">
          <input v-model="form.tax_rate" type="number" step="0.0001" min="0" max="1" class="rounded-lg border px-3 py-2 text-sm" placeholder="Tax rate (0.0875)">
          <input v-model="form.delivery_fee" type="number" step="0.01" min="0" class="rounded-lg border px-3 py-2 text-sm" placeholder="Delivery fee">
        </div>
      </section>

      <p v-if="message" class="text-sm" :class="message === 'Settings saved' ? 'text-brand-700' : 'text-red-600'">{{ message }}</p>
      <AppButton type="submit" :disabled="saving">{{ saving ? 'Saving…' : 'Save settings' }}</AppButton>
    </form>
  </div>
</template>
