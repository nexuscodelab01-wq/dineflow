<script setup lang="ts">
import type { Restaurant } from '~/types/menu'
import { fetchAdminSettings, updateAdminSettings, uploadGalleryImage, uploadLogo } from '~/services/admin'
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

const gallery = ref<string[]>([])
const uploadingGallery = ref(false)
const galleryError = ref('')

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
  min_party_size: 1,
  max_party_size: null as number | null,
  max_covers_per_slot: null as number | null,
  booking_lead_time_minutes: 0,
  custom_domain: '',
  primary_color: '',
  secondary_color: '',
  about_text: '',
  social_links: { instagram: '', facebook: '', twitter: '', tiktok: '', youtube: '' },
  latitude: '',
  longitude: '',
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
    gallery.value = [...(settings.value.gallery ?? [])]
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
      min_party_size: settings.value.min_party_size ?? 1,
      max_party_size: settings.value.max_party_size ?? null,
      max_covers_per_slot: settings.value.max_covers_per_slot ?? null,
      booking_lead_time_minutes: settings.value.booking_lead_time_minutes ?? 0,
      custom_domain: settings.value.custom_domain || '',
      primary_color: settings.value.primary_color || '',
      secondary_color: settings.value.secondary_color || '',
      about_text: settings.value.about_text || '',
      social_links: {
        instagram: settings.value.social_links?.instagram || '',
        facebook: settings.value.social_links?.facebook || '',
        twitter: settings.value.social_links?.twitter || '',
        tiktok: settings.value.social_links?.tiktok || '',
        youtube: settings.value.social_links?.youtube || '',
      },
      latitude: settings.value.latitude || '',
      longitude: settings.value.longitude || '',
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

const MAX_GALLERY_IMAGES = 20

async function onGallerySelected(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file || !admin.restaurantId) return
  galleryError.value = ''
  if (!/^image\/(png|jpeg|webp|gif)$/.test(file.type)) {
    galleryError.value = 'Use a PNG, JPEG, WebP or GIF image'
    return
  }
  if (file.size > MAX_LOGO_BYTES) {
    galleryError.value = 'The image must be 5MB or smaller'
    return
  }
  if (gallery.value.length >= MAX_GALLERY_IMAGES) {
    galleryError.value = `Up to ${MAX_GALLERY_IMAGES} photos`
    return
  }
  uploadingGallery.value = true
  try {
    const { url } = await uploadGalleryImage(admin.restaurantId, file)
    const updated = await updateAdminSettings(admin.restaurantId, { gallery: [...gallery.value, url] })
    gallery.value = [...(updated.gallery ?? [])]
    message.value = 'Photo added'
  }
  catch (err) {
    galleryError.value = err instanceof Error ? err.message : 'Upload failed'
  }
  finally {
    uploadingGallery.value = false
  }
}

async function removeGalleryImage(url: string) {
  if (!admin.restaurantId) return
  galleryError.value = ''
  try {
    const updated = await updateAdminSettings(admin.restaurantId, { gallery: gallery.value.filter(g => g !== url) })
    gallery.value = [...(updated.gallery ?? [])]
    message.value = 'Photo removed'
  }
  catch (err) {
    galleryError.value = err instanceof Error ? err.message : 'Could not remove the photo'
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
      // An emptied number input leaves the ref as '' rather than null.
      max_party_size: form.max_party_size === '' || form.max_party_size == null ? null : Number(form.max_party_size),
      max_covers_per_slot: form.max_covers_per_slot === '' || form.max_covers_per_slot == null ? null : Number(form.max_covers_per_slot),
      about_text: form.about_text || null,
      social_links: Object.fromEntries(Object.entries(form.social_links).filter(([, v]) => v.trim())),
      latitude: form.latitude === '' ? null : form.latitude,
      longitude: form.longitude === '' ? null : form.longitude,
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

        <div class="grid gap-3 border-t border-brand-100 pt-4 sm:grid-cols-2">
          <label class="block text-sm font-medium">Primary colour <span class="font-normal text-ink-subtle">(buttons, links)</span>
            <div class="mt-1 flex items-center gap-2">
              <input v-model="form.primary_color" type="color" class="h-9 w-14 cursor-pointer rounded border">
              <input v-model="form.primary_color" type="text" class="w-full rounded-lg border px-3 py-2 text-sm" placeholder="#2c6f53">
            </div>
          </label>
          <label class="block text-sm font-medium">Secondary colour <span class="font-normal text-ink-subtle">(badges — optional)</span>
            <div class="mt-1 flex items-center gap-2">
              <input v-model="form.secondary_color" type="color" class="h-9 w-14 cursor-pointer rounded border">
              <input v-model="form.secondary_color" type="text" class="w-full rounded-lg border px-3 py-2 text-sm" placeholder="#f1c40f">
            </div>
          </label>
        </div>
        <p class="text-xs text-ink-subtle">Colours only show on your site once "Custom branding" is turned on for your restaurant (ask us if it isn't).</p>
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

      <section class="rounded-2xl border border-brand-100 bg-surface-elevated p-6 space-y-4">
        <div>
          <h2 class="font-semibold">Home page</h2>
          <p class="mt-1 text-xs text-ink-subtle">About us, photos, social links and a map for your site's home page.</p>
        </div>

        <label class="block text-sm font-medium">About us
          <textarea v-model="form.about_text" rows="4" class="mt-1 w-full rounded-lg border px-3 py-2 text-sm" placeholder="Tell guests your story — when you opened, what makes your food special…" />
        </label>

        <div class="border-t border-brand-100 pt-4">
          <h3 class="text-sm font-semibold">Photo gallery</h3>
          <div v-if="gallery.length" class="mt-3 grid grid-cols-3 gap-2 sm:grid-cols-4">
            <div v-for="url in gallery" :key="url" class="group relative aspect-square overflow-hidden rounded-lg border border-brand-100 bg-white">
              <img :src="resolveMediaUrl(url)!" alt="" class="h-full w-full object-cover">
              <button
                type="button"
                class="absolute right-1 top-1 rounded-full bg-black/60 px-1.5 py-0.5 text-xs text-white opacity-0 transition group-hover:opacity-100"
                aria-label="Remove photo"
                @click="removeGalleryImage(url)"
              >
                ×
              </button>
            </div>
          </div>
          <label class="mt-3 inline-block cursor-pointer rounded-lg border border-brand-200 px-3 py-2 text-sm font-medium hover:bg-brand-50">
            {{ uploadingGallery ? 'Uploading…' : 'Add a photo' }}
            <input type="file" accept="image/png,image/jpeg,image/webp,image/gif" class="hidden" :disabled="uploadingGallery" @change="onGallerySelected">
          </label>
          <p class="mt-1 text-xs text-ink-subtle">Up to {{ MAX_GALLERY_IMAGES }} photos, 5MB each.</p>
          <p v-if="galleryError" class="text-sm text-red-600" role="alert">{{ galleryError }}</p>
        </div>

        <div class="border-t border-brand-100 pt-4">
          <h3 class="text-sm font-semibold">Social links <span class="font-normal text-ink-subtle">(optional)</span></h3>
          <div class="mt-3 grid gap-3 sm:grid-cols-2">
            <input v-model="form.social_links.instagram" class="rounded-lg border px-3 py-2 text-sm" placeholder="Instagram URL">
            <input v-model="form.social_links.facebook" class="rounded-lg border px-3 py-2 text-sm" placeholder="Facebook URL">
            <input v-model="form.social_links.twitter" class="rounded-lg border px-3 py-2 text-sm" placeholder="X / Twitter URL">
            <input v-model="form.social_links.tiktok" class="rounded-lg border px-3 py-2 text-sm" placeholder="TikTok URL">
            <input v-model="form.social_links.youtube" class="rounded-lg border px-3 py-2 text-sm" placeholder="YouTube URL">
          </div>
        </div>

        <div class="border-t border-brand-100 pt-4">
          <h3 class="text-sm font-semibold">Map <span class="font-normal text-ink-subtle">(optional)</span></h3>
          <p class="mt-1 text-xs text-ink-subtle">
            Add coordinates to show an interactive map on your home page — otherwise it just shows your address as text.
            <a href="https://www.google.com/maps" target="_blank" rel="noopener" class="text-brand-700 underline">Find yours on Google Maps</a>:
            right-click your location, then click the coordinates to copy them.
          </p>
          <div class="mt-3 grid gap-3 sm:grid-cols-2">
            <input v-model="form.latitude" type="number" step="0.000001" min="-90" max="90" class="rounded-lg border px-3 py-2 text-sm" placeholder="Latitude, e.g. 40.712800">
            <input v-model="form.longitude" type="number" step="0.000001" min="-180" max="180" class="rounded-lg border px-3 py-2 text-sm" placeholder="Longitude, e.g. -74.006000">
          </div>
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

      <section class="rounded-2xl border border-brand-100 bg-surface-elevated p-6 space-y-4">
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

        <div class="border-t border-brand-100 pt-4">
          <h3 class="text-sm font-semibold">Guest booking limits</h3>
          <p class="mt-1 text-xs text-ink-subtle">Staff can still book outside these from the admin side — for private events or corrections.</p>
          <div class="mt-3 grid gap-3 sm:grid-cols-3">
            <label class="block text-sm">
              <span class="mb-1 block font-medium">Min party size</span>
              <input v-model.number="form.min_party_size" type="number" min="1" max="20" class="w-full rounded-lg border px-3 py-2 text-sm">
            </label>
            <label class="block text-sm">
              <span class="mb-1 block font-medium">Max party size <span class="font-normal text-ink-subtle">(blank = no limit)</span></span>
              <input v-model.number="form.max_party_size" type="number" min="1" max="20" placeholder="—" class="w-full rounded-lg border px-3 py-2 text-sm">
            </label>
            <label class="block text-sm">
              <span class="mb-1 block font-medium">Minimum notice (minutes)</span>
              <input v-model.number="form.booking_lead_time_minutes" type="number" min="0" step="15" class="w-full rounded-lg border px-3 py-2 text-sm">
              <span class="mt-1 block text-xs text-ink-subtle">0 allows booking right up to the start time.</span>
            </label>
            <label class="block text-sm">
              <span class="mb-1 block font-medium">Max covers per 15 min <span class="font-normal text-ink-subtle">(blank = no limit)</span></span>
              <input v-model.number="form.max_covers_per_slot" type="number" min="1" placeholder="—" class="w-full rounded-lg border px-3 py-2 text-sm">
              <span class="mt-1 block text-xs text-ink-subtle">Caps total guests arriving in the same 15 minutes — protects the kitchen even when tables are free.</span>
            </label>
          </div>
        </div>
      </section>

      <p v-if="message" class="text-sm" :class="message === 'Settings saved' ? 'text-brand-700' : 'text-red-600'">{{ message }}</p>
      <AppButton type="submit" :disabled="saving">{{ saving ? 'Saving…' : 'Save settings' }}</AppButton>
    </form>
  </div>
</template>
