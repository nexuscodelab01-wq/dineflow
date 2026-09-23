<script setup lang="ts">
// A restaurant's own home page — the tenant middleware guarantees a restaurant has resolved by the
// time this renders (an unknown address shows the "no restaurant here" error page instead).
import { resolveMediaUrl } from '~/utils/media'

const restaurant = useRestaurantStore()
const branding = useBranding()
const { status: openStatus } = useOpeningStatus()
const current = computed(() => restaurant.current)

const fullAddress = computed(() => {
  if (!current.value?.address) return null
  return current.value.city ? `${current.value.address}, ${current.value.city}` : current.value.address
})

const hasCoords = computed(() => current.value?.latitude != null && current.value?.longitude != null)
// A small fixed-size box around the point — plenty close for a single-location restaurant.
const mapEmbedUrl = computed(() => {
  if (!hasCoords.value) return null
  const lat = Number(current.value!.latitude)
  const lon = Number(current.value!.longitude)
  const d = 0.006
  return `https://www.openstreetmap.org/export/embed.html?bbox=${lon - d}%2C${lat - d}%2C${lon + d}%2C${lat + d}&layer=mapnik&marker=${lat}%2C${lon}`
})
const directionsUrl = computed(() => {
  if (hasCoords.value) return `https://www.google.com/maps/search/?api=1&query=${current.value!.latitude}%2C${current.value!.longitude}`
  if (fullAddress.value) return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(fullAddress.value)}`
  return null
})

const socialLinks = computed(() => {
  const s = current.value?.social_links || {}
  const labels: Record<string, string> = { instagram: 'Instagram', facebook: 'Facebook', twitter: 'X / Twitter', tiktok: 'TikTok', youtube: 'YouTube' }
  return Object.entries(s)
    .filter((entry): entry is [string, string] => Boolean(entry[1]))
    .map(([key, url]) => ({ key, url, label: labels[key] || key }))
})

const hasContactSection = computed(() =>
  Boolean(current.value?.phone || current.value?.email || fullAddress.value || hasCoords.value || socialLinks.value.length),
)
</script>

<template>
  <div>
    <section class="relative overflow-hidden">
      <div
        class="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,_var(--color-brand-100)_0%,_transparent_55%),radial-gradient(ellipse_at_bottom_left,_var(--color-brand-50)_0%,_transparent_50%)]"
        aria-hidden="true"
      />
      <div class="relative mx-auto flex max-w-6xl flex-col items-start gap-6 px-4 py-20 sm:px-6 sm:py-28">
        <img v-if="branding.logo.value" :src="branding.logo.value" :alt="current?.name" class="h-16 w-auto max-w-[16rem] object-contain sm:h-20">

        <p v-if="current?.opening_hours" class="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold" :class="openStatus.open ? 'bg-emerald-100 text-emerald-900' : 'bg-amber-100 text-amber-900'">
          <span class="h-2 w-2 rounded-full" :class="openStatus.open ? 'bg-emerald-500' : 'bg-amber-500'" />
          {{ openStatus.open ? 'Open now' : 'Closed now' }}
        </p>

        <h1 class="font-display max-w-2xl text-4xl font-semibold leading-tight text-brand-900 sm:text-5xl md:text-6xl">
          {{ current?.name ?? 'Welcome' }}
        </h1>
        <p class="max-w-xl text-lg leading-relaxed text-ink-muted">
          {{ current?.description || 'Order online, or book a table — we\'d love to have you.' }}
        </p>
        <p v-if="fullAddress" class="text-sm text-ink-subtle">{{ fullAddress }}</p>

        <div class="flex flex-wrap items-center gap-3 pt-2">
          <NuxtLink
            to="/menu"
            class="inline-flex items-center justify-center rounded-lg bg-brand-700 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-brand-800"
          >
            Browse menu
          </NuxtLink>
          <NuxtLink
            v-if="current?.dine_in_enabled"
            to="/reserve"
            class="inline-flex items-center rounded-lg border border-brand-200 bg-surface-elevated px-5 py-2.5 text-sm font-semibold text-ink hover:bg-brand-50"
          >
            Book a table
          </NuxtLink>
        </div>
      </div>
    </section>

    <section v-if="current?.gallery?.length" class="mx-auto max-w-6xl px-4 py-14 sm:px-6">
      <h2 class="font-display text-2xl font-semibold text-brand-900 sm:text-3xl">Gallery</h2>
      <div class="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
        <img
          v-for="url in current.gallery" :key="url"
          :src="resolveMediaUrl(url)!" alt=""
          loading="lazy"
          class="aspect-square w-full rounded-xl object-cover"
        >
      </div>
    </section>

    <section v-if="current?.about_text" class="border-t border-brand-100 bg-surface-muted/40">
      <div class="mx-auto max-w-3xl px-4 py-14 text-center sm:px-6">
        <h2 class="font-display text-2xl font-semibold text-brand-900 sm:text-3xl">About us</h2>
        <p class="mt-4 whitespace-pre-line text-lg leading-relaxed text-ink-muted">{{ current.about_text }}</p>
      </div>
    </section>

    <section v-if="hasContactSection" class="border-t border-brand-100">
      <div class="mx-auto grid max-w-6xl gap-10 px-4 py-14 sm:px-6 md:grid-cols-2">
        <div>
          <h2 class="font-display text-2xl font-semibold text-brand-900 sm:text-3xl">Visit us</h2>
          <dl class="mt-6 space-y-4 text-sm">
            <div v-if="fullAddress || directionsUrl">
              <dt class="font-semibold text-ink">Address</dt>
              <dd v-if="fullAddress" class="mt-0.5 text-ink-muted">{{ fullAddress }}</dd>
              <a v-if="directionsUrl" :href="directionsUrl" target="_blank" rel="noopener" class="mt-1 inline-block text-brand-700 underline">Get directions</a>
            </div>
            <div v-if="current?.phone">
              <dt class="font-semibold text-ink">Phone</dt>
              <dd class="mt-0.5"><a :href="`tel:${current.phone}`" class="text-brand-700 underline">{{ current.phone }}</a></dd>
            </div>
            <div v-if="current?.email">
              <dt class="font-semibold text-ink">Email</dt>
              <dd class="mt-0.5"><a :href="`mailto:${current.email}`" class="text-brand-700 underline">{{ current.email }}</a></dd>
            </div>
            <div v-if="socialLinks.length">
              <dt class="font-semibold text-ink">Follow us</dt>
              <dd class="mt-1 flex flex-wrap gap-3">
                <a v-for="s in socialLinks" :key="s.key" :href="s.url" target="_blank" rel="noopener" class="text-brand-700 underline">{{ s.label }}</a>
              </dd>
            </div>
          </dl>
        </div>

        <iframe
          v-if="mapEmbedUrl"
          :src="mapEmbedUrl"
          title="Map"
          loading="lazy"
          class="h-64 w-full rounded-xl border border-brand-100 md:h-full"
        />
        <div v-else-if="fullAddress" class="flex h-64 items-center justify-center rounded-xl border border-brand-100 bg-surface-muted/60 text-center text-sm text-ink-subtle md:h-full">
          <div class="px-6">
            <p>{{ fullAddress }}</p>
            <a v-if="directionsUrl" :href="directionsUrl" target="_blank" rel="noopener" class="mt-2 inline-block font-medium text-brand-700 underline">Get directions</a>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>
