<script setup lang="ts">
import type { Restaurant } from '~/types/menu'
import { fetchAdminSettings, updateAdminSettings, uploadLogo } from '~/services/admin'
import { resolveMediaUrl } from '~/utils/media'
import { DAYS, type Day, parseDay } from '~/utils/hours'
import { COMMON_TIMEZONES } from '~/utils/timezones'

definePageMeta({ layout: 'admin', middleware: ['admin'] })

const admin = useAdminStore()
const settings = ref<Restaurant | null>(null)
const loading = ref(true)
const saving = ref(false)
const message = ref('')

const logoUrl = ref<string | null>(null)
const uploadingLogo = ref(false)
const logoError = ref('')

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
  reservation_buffer_minutes: 15,
  custom_domain: '',
})

const dayLabels: Record<Day, string> = {
  monday: 'Monday', tuesday: 'Tuesday', wednesday: 'Wednesday', thursday: 'Thursday',
  friday: 'Friday', saturday: 'Saturday', sunday: 'Sunday',
}

type DayHours = { closed: boolean, open: string, close: string }
const hours = reactive<Record<Day, DayHours>>(
  Object.fromEntries(DAYS.map(d => [d, { closed: true, open: '11:00', close: '22:00' }])) as Record<Day, DayHours>,
)

const timezone = ref('UTC')
const customTimezone = ref(false)

const closures = ref<{ date: string, label: string }[]>([])
const newClosureDate = ref('')
const newClosureLabel = ref('')

function applyOpeningHours(source: Record<string, string> | null | undefined) {
  for (const day of DAYS) {
    const window = source ? parseDay(source[day]) : null
    if (window) {
      const fmt = (m: number) => `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`
      hours[day] = { closed: false, open: fmt(window[0]), close: fmt(window[1]) }
    }
    else {
      hours[day] = { closed: true, open: '11:00', close: '22:00' }
    }
  }
}

onMounted(async () => {
  await admin.initialize()
  if (admin.restaurantId) {
    settings.value = await fetchAdminSettings(admin.restaurantId)
    logoUrl.value = settings.value.logo_url ?? null
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
      reservation_buffer_minutes: settings.value.reservation_buffer_minutes ?? 15,
      custom_domain: settings.value.custom_domain || '',
    })
    timezone.value = settings.value.timezone || 'UTC'
    customTimezone.value = !COMMON_TIMEZONES.some(t => t.value === timezone.value)
    applyOpeningHours(settings.value.opening_hours)
    closures.value = (settings.value.closures ?? []).map(c => ({ date: c.date, label: c.label ?? '' })).sort((a, b) => a.date.localeCompare(b.date))
  }
  loading.value = false
})

const MAX_LOGO_BYTES = 5 * 1024 * 1024

async function onLogoSelected(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = '' // let the same file be picked again
  if (!file || !admin.restaurantId) return
  logoError.value = ''
  if (!/^image\/(png|jpeg|webp|gif)$/.test(file.type)) {
    logoError.value = 'Use a PNG, JPEG, WebP or GIF image'
    return
  }
  if (file.size > MAX_LOGO_BYTES) {
    logoError.value = 'The image must be 5MB or smaller'
    return
  }
  uploadingLogo.value = true
  try {
    const { url } = await uploadLogo(admin.restaurantId, file)
    // Attach it right away so an uploaded logo is never left orphaned.
    const updated = await updateAdminSettings(admin.restaurantId, { logo_url: url })
    logoUrl.value = updated.logo_url ?? null
    message.value = 'Logo updated'
  }
  catch (err) {
    logoError.value = err instanceof Error ? err.message : 'Upload failed'
  }
  finally {
    uploadingLogo.value = false
  }
}

async function removeLogo() {
  if (!admin.restaurantId) return
  logoError.value = ''
  try {
    const updated = await updateAdminSettings(admin.restaurantId, { logo_url: null })
    logoUrl.value = updated.logo_url ?? null
    message.value = 'Logo removed'
  }
  catch (err) {
    logoError.value = err instanceof Error ? err.message : 'Could not remove the logo'
  }
}

function addClosure() {
  if (!newClosureDate.value) return
  if (closures.value.some(c => c.date === newClosureDate.value)) {
    message.value = 'That date is already in the list'
    return
  }
  closures.value = [...closures.value, { date: newClosureDate.value, label: newClosureLabel.value.trim() }].sort((a, b) => a.date.localeCompare(b.date))
  newClosureDate.value = ''
  newClosureLabel.value = ''
}

function removeClosure(date: string) {
  closures.value = closures.value.filter(c => c.date !== date)
}

async function save() {
  if (!admin.restaurantId) return
  saving.value = true
  message.value = ''
  try {
    const openingHours = Object.fromEntries(
      DAYS.map(day => [day, hours[day].closed ? 'closed' : `${hours[day].open}-${hours[day].close}`]),
    )
    settings.value = await updateAdminSettings(admin.restaurantId, {
      ...form,
      tax_rate: form.tax_rate,
      delivery_fee: form.delivery_fee,
      timezone: timezone.value,
      opening_hours: openingHours,
      closures: closures.value.map(c => ({ date: c.date, label: c.label || null })),
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
    <p class="text-sm text-ink-muted">Profile, ordering options, hours and fees</p>

    <div v-if="loading" class="mt-6 h-64 animate-pulse rounded-2xl bg-brand-100/60" />

    <form v-else class="mt-6 max-w-2xl space-y-6" @submit.prevent="save">
      <section class="rounded-2xl border border-brand-100 bg-surface-elevated p-6 space-y-3">
        <h2 class="font-semibold">Logo</h2>
        <div class="flex flex-wrap items-center gap-4">
          <div class="flex h-20 w-20 items-center justify-center overflow-hidden rounded-xl border border-brand-100 bg-white">
            <img v-if="resolveMediaUrl(logoUrl)" :src="resolveMediaUrl(logoUrl)!" alt="Restaurant logo" class="max-h-full max-w-full object-contain" data-testid="logo-preview">
            <span v-else class="px-2 text-center text-xs text-ink-subtle">No logo</span>
          </div>
          <div class="space-y-2">
            <label class="inline-block cursor-pointer rounded-lg border border-brand-200 px-3 py-2 text-sm font-medium hover:bg-brand-50">
              {{ uploadingLogo ? 'Uploading…' : logoUrl ? 'Replace logo' : 'Upload logo' }}
              <input type="file" accept="image/png,image/jpeg,image/webp,image/gif" class="hidden" :disabled="uploadingLogo" data-testid="logo-input" @change="onLogoSelected">
            </label>
            <button v-if="logoUrl" type="button" class="ml-3 text-sm text-red-600 hover:underline" @click="removeLogo">Remove</button>
            <p class="text-xs text-ink-subtle">PNG with a transparent background works best. Max 5MB.</p>
          </div>
        </div>
        <p v-if="logoError" class="text-sm text-red-600" role="alert">{{ logoError }}</p>
      </section>

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

      <section class="rounded-2xl border border-brand-100 bg-surface-elevated p-6 space-y-3">
        <h2 class="font-semibold">Custom domain</h2>
        <p class="text-xs text-ink-subtle">Point your own domain at your site (e.g. order.yourrestaurant.com). Point its DNS at this platform, then ask us to verify it.</p>
        <input v-model="form.custom_domain" class="w-full rounded-lg border px-3 py-2 text-sm" placeholder="order.yourrestaurant.com">
        <p v-if="settings?.custom_domain" class="text-sm">
          <span v-if="settings.domain_verified_at" class="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-semibold text-emerald-900">Verified</span>
          <span v-else class="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-900">Pending verification</span>
        </p>
      </section>

      <section class="rounded-2xl border border-brand-100 bg-surface-elevated p-6 space-y-4">
        <div>
          <h2 class="font-semibold">Hours &amp; timezone</h2>
          <p class="mt-1 text-xs text-ink-subtle">
            Ordering and booking are refused outside these hours (a day left off or marked closed is closed all day). Leave every day closed to stay open around the clock.
          </p>
        </div>

        <label class="block text-sm font-medium">Timezone
          <select v-if="!customTimezone" v-model="timezone" class="mt-1 w-full rounded-lg border px-3 py-2 text-sm">
            <option v-for="tz in COMMON_TIMEZONES" :key="tz.value" :value="tz.value">{{ tz.label }}</option>
          </select>
          <input v-else v-model="timezone" class="mt-1 w-full rounded-lg border px-3 py-2 text-sm" placeholder="e.g. Europe/Lisbon">
        </label>
        <button type="button" class="text-xs font-medium text-brand-700 hover:underline" @click="customTimezone = !customTimezone">
          {{ customTimezone ? 'Choose from the list instead' : 'My timezone isn’t listed' }}
        </button>

        <div class="space-y-2">
          <div v-for="day in DAYS" :key="day" class="flex flex-wrap items-center gap-3 rounded-lg border border-brand-100 px-3 py-2">
            <span class="w-24 shrink-0 text-sm font-medium">{{ dayLabels[day] }}</span>
            <label class="flex items-center gap-1.5 text-xs text-ink-muted">
              <input v-model="hours[day].closed" type="checkbox" :data-testid="`closed-${day}`"> Closed
            </label>
            <template v-if="!hours[day].closed">
              <input v-model="hours[day].open" type="time" class="rounded-md border px-2 py-1 text-sm" :data-testid="`open-${day}`">
              <span class="text-ink-subtle">to</span>
              <input v-model="hours[day].close" type="time" class="rounded-md border px-2 py-1 text-sm" :data-testid="`close-${day}`">
            </template>
          </div>
        </div>

        <div class="border-t border-brand-100 pt-4">
          <h3 class="text-sm font-semibold">Closed on specific dates</h3>
          <p class="mt-1 text-xs text-ink-subtle">Holidays, private events — closed all day, whatever the weekly hours say.</p>
          <ul v-if="closures.length" class="mt-3 space-y-1.5">
            <li v-for="c in closures" :key="c.date" class="flex items-center justify-between gap-2 rounded-lg bg-surface-muted/60 px-3 py-1.5 text-sm">
              <span><strong>{{ c.date }}</strong><span v-if="c.label"> — {{ c.label }}</span></span>
              <button type="button" class="text-xs font-medium text-red-600 hover:underline" @click="removeClosure(c.date)">Remove</button>
            </li>
          </ul>
          <div class="mt-3 flex flex-wrap items-end gap-2">
            <label class="text-xs font-medium">Date
              <input v-model="newClosureDate" type="date" class="mt-1 block rounded-lg border px-2 py-1.5 text-sm">
            </label>
            <label class="flex-1 text-xs font-medium">Reason (optional)
              <input v-model="newClosureLabel" type="text" maxlength="100" placeholder="e.g. Christmas Day" class="mt-1 w-full rounded-lg border px-2 py-1.5 text-sm">
            </label>
            <button type="button" class="rounded-lg border border-brand-200 px-3 py-1.5 text-sm font-medium hover:bg-brand-50" :disabled="!newClosureDate" @click="addClosure">Add</button>
          </div>
        </div>
      </section>

      <section class="rounded-2xl border border-brand-100 bg-surface-elevated p-6 space-y-3">
        <h2 class="font-semibold">Reservations</h2>
        <label class="block text-sm">
          <span class="mb-1 block font-medium">Reset gap between bookings (minutes)</span>
          <input
            v-model.number="form.reservation_buffer_minutes"
            type="number"
            min="0"
            max="60"
            step="5"
            class="w-40 rounded-lg border px-3 py-2 text-sm"
          >
          <span class="mt-1 block text-xs text-ink-subtle">
            A table is held free this long after each booking — time to clear it, and slack for guests who run over.
            0 allows back-to-back bookings.
          </span>
        </label>
      </section>

      <p v-if="message" class="text-sm" :class="message === 'Settings saved' ? 'text-brand-700' : 'text-red-600'">{{ message }}</p>
      <AppButton type="submit" :disabled="saving">{{ saving ? 'Saving…' : 'Save settings' }}</AppButton>
    </form>
  </div>
</template>
