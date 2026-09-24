<script setup lang="ts">
// A restaurant's own home page — the tenant middleware guarantees a restaurant has resolved by the
// time this renders (an unknown address shows the "no restaurant here" error page instead).
import type { MenuItem } from '~/types/menu'
import type { PublicReview } from '~/types/review'
import { fetchMenu } from '~/services/menu'
import { fetchPublicReviews } from '~/services/reviews'
import { resolveMediaUrl } from '~/utils/media'
import { formatCurrency } from '~/utils/format'
import { wallClockIn } from '~/utils/timezone'
import { weeklyHoursLabels } from '~/utils/hours'

const restaurant = useRestaurantStore()
const { status: openStatus, todayLabel } = useOpeningStatus()
const current = computed(() => restaurant.current)
const reviewsEnabled = useFeature('reviews')

// A handful of popular dishes give the home page something real to show beyond stock copy — fetched
// once alongside the restaurant itself so it's there on first paint, not a layout jump after mount.
const popularItems = ref<MenuItem[]>([])
if (current.value) {
  try {
    const res = await fetchMenu(current.value.id, { is_popular: true, page_size: 8 })
    popularItems.value = res.items
  }
  catch {
    // Decorative — a failed fetch just means no "Popular dishes" section, not a broken page.
  }
}

// Reviews: fetched client-side only when the flag is on, so a tenant with it off never pays for the request.
const reviews = ref<PublicReview[]>([])
const averageRating = ref<number | null>(null)
const reviewCount = ref(0)
onMounted(async () => {
  if (!reviewsEnabled.value || !current.value) return
  try {
    const res = await fetchPublicReviews(current.value.slug, 1, 6)
    reviews.value = res.items
    averageRating.value = res.average_rating
    reviewCount.value = res.total
  }
  catch {
    // Decorative — a failed fetch just means no "Reviews" section.
  }
})

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

const weeklyHours = computed(() => {
  if (!current.value?.opening_hours) return []
  const todayIndex = (wallClockIn(current.value.timezone || 'UTC').getDay() + 6) % 7
  return weeklyHoursLabels(current.value.opening_hours, todayIndex)
})

const serviceHighlights = computed(() => {
  if (!current.value) return []
  return [
    current.value.dine_in_enabled && { key: 'dine-in', label: 'Dine-in' },
    current.value.pickup_enabled && { key: 'pickup', label: 'Pickup' },
    current.value.delivery_enabled && { key: 'delivery', label: 'Delivery' },
  ].filter((x): x is { key: string, label: string } => Boolean(x))
})

// ---- hero photo slideshow (falls back to the plain gradient hero when there's no gallery) --------

const gallery = computed(() => current.value?.gallery ?? [])
const heroSlides = computed(() => gallery.value.slice(0, 5))
const heroIndex = ref(0)
let heroTimer: ReturnType<typeof setInterval> | undefined
onMounted(() => {
  if (heroSlides.value.length > 1) {
    heroTimer = setInterval(() => { heroIndex.value = (heroIndex.value + 1) % heroSlides.value.length }, 6000)
  }
})
onUnmounted(() => { if (heroTimer) clearInterval(heroTimer) })
</script>

<template>
  <div>
    <!-- Hero -->
    <section class="relative flex items-center overflow-hidden" :class="heroSlides.length ? 'min-h-[86vh]' : 'min-h-[58vh]'">
      <template v-if="heroSlides.length">
        <div class="absolute inset-0">
          <img
            v-for="(url, i) in heroSlides" :key="url"
            :src="resolveMediaUrl(url)!" alt=""
            class="animate-ken-burns absolute inset-0 h-full w-full object-cover transition-opacity duration-[1600ms] ease-in-out"
            :class="i === heroIndex ? 'opacity-100' : 'opacity-0'"
          >
          <div class="absolute inset-0 bg-gradient-to-br from-black/65 via-black/40 to-black/60" aria-hidden="true" />
        </div>
      </template>
      <div
        v-else
        class="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,_var(--color-brand-100)_0%,_transparent_55%),radial-gradient(ellipse_at_bottom_left,_var(--color-brand-50)_0%,_transparent_50%)]"
        aria-hidden="true"
      />

      <div class="relative mx-auto w-full max-w-6xl px-4 py-24 sm:px-6">
        <div
          class="max-w-xl rounded-[1.75rem] p-8 sm:p-10"
          :class="heroSlides.length
            ? 'border border-white/20 bg-gradient-to-br from-white/[0.18] to-white/[0.06] shadow-2xl shadow-black/40 ring-1 ring-inset ring-white/10 backdrop-blur-2xl'
            : ''"
        >
          <p
            v-if="current?.opening_hours"
            class="inline-flex items-center gap-2 rounded-full px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.15em]"
            :class="heroSlides.length
              ? 'border border-white/25 bg-white/10 text-white backdrop-blur-sm'
              : (openStatus.open ? 'bg-emerald-100 text-emerald-900' : 'bg-amber-100 text-amber-900')"
          >
            <span class="h-1.5 w-1.5 rounded-full" :class="openStatus.open ? 'bg-emerald-400' : 'bg-amber-400'" />
            {{ openStatus.open ? 'Open now' : 'Closed now' }}
          </p>

          <h1
            class="font-display mt-5 text-[2.75rem] font-semibold leading-[1.05] tracking-tight sm:text-6xl"
            :class="heroSlides.length ? 'text-white' : 'text-brand-900'"
          >
            {{ current?.name ?? 'Welcome' }}
          </h1>

          <p class="mt-5 text-lg leading-relaxed" :class="heroSlides.length ? 'text-white/85' : 'text-ink-muted'">
            {{ current?.description || 'Order online, or book a table — we\'d love to have you.' }}
          </p>

          <p
            v-if="fullAddress"
            class="mt-4 inline-flex items-center gap-2 text-sm"
            :class="heroSlides.length ? 'text-white/70' : 'text-ink-subtle'"
          >
            <svg viewBox="0 0 24 24" class="h-4 w-4 shrink-0" fill="none" stroke="currentColor" stroke-width="1.75"><path stroke-linecap="round" stroke-linejoin="round" d="M12 21s7-5.686 7-11a7 7 0 1 0-14 0c0 5.314 7 11 7 11Z" /><circle cx="12" cy="10" r="2.5" /></svg>
            {{ fullAddress }}
          </p>

          <div class="mt-8 flex flex-wrap items-center gap-3">
            <NuxtLink
              to="/menu"
              class="inline-flex items-center justify-center rounded-full bg-brand-700 px-7 py-3 text-sm font-semibold text-white shadow-lg shadow-brand-900/30 transition duration-300 hover:-translate-y-0.5 hover:bg-brand-800 hover:shadow-xl"
            >
              Browse menu
            </NuxtLink>
            <NuxtLink
              v-if="current?.dine_in_enabled"
              to="/reserve"
              class="inline-flex items-center rounded-full border px-7 py-3 text-sm font-semibold transition duration-300 hover:-translate-y-0.5"
              :class="heroSlides.length
                ? 'border-white/30 bg-white/10 text-white backdrop-blur-md hover:bg-white/20'
                : 'border-brand-200 bg-surface-elevated text-ink hover:bg-brand-50'"
            >
              Book a table
            </NuxtLink>
          </div>
        </div>
      </div>

      <!-- Slide dots: a rail down the right edge on desktop, out of the way of the gallery pill on phones -->
      <div
        v-if="heroSlides.length > 1"
        class="absolute bottom-8 left-4 z-10 flex gap-2 sm:bottom-auto sm:left-auto sm:right-7 sm:top-1/2 sm:-translate-y-1/2 sm:flex-col sm:items-center"
      >
        <button
          v-for="(url, i) in heroSlides" :key="url" type="button"
          class="rounded-full transition-all duration-500"
          :class="i === heroIndex ? 'h-1.5 w-8 bg-white sm:h-10 sm:w-1.5' : 'h-1.5 w-1.5 bg-white/40 hover:bg-white/70'"
          :aria-label="`Show photo ${i + 1}`" @click="heroIndex = i"
        />
      </div>

      <!-- Gallery entry point -->
      <NuxtLink
        v-if="gallery.length"
        to="/gallery"
        class="group absolute bottom-6 right-4 z-10 inline-flex items-center gap-2.5 rounded-full border border-white/25 bg-white/10 py-2.5 pl-4 pr-3 text-sm font-semibold text-white shadow-lg shadow-black/20 backdrop-blur-xl transition duration-300 hover:-translate-y-0.5 hover:bg-white/20 sm:bottom-8 sm:right-8"
      >
        <svg viewBox="0 0 24 24" class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="1.75"><rect x="3" y="5" width="18" height="14" rx="2.5" /><circle cx="8.5" cy="10" r="1.5" /><path stroke-linecap="round" stroke-linejoin="round" d="m4 17 5-5 4 4 2.5-2.5L20 17" /></svg>
        Gallery
        <span class="rounded-full bg-white/15 px-2 py-0.5 text-xs font-medium tabular-nums">{{ gallery.length }}</span>
      </NuxtLink>
    </section>

    <!-- Services / hours strip -->
    <section v-if="serviceHighlights.length || todayLabel" class="border-b border-brand-100 bg-surface-elevated">
      <div class="mx-auto flex max-w-6xl flex-wrap items-center justify-center gap-x-12 gap-y-3 px-4 py-6 text-sm font-medium text-ink-muted sm:px-6">
        <span v-for="s in serviceHighlights" :key="s.key" class="inline-flex items-center gap-2.5">
          <svg v-if="s.key === 'dine-in'" viewBox="0 0 24 24" class="h-[18px] w-[18px] text-brand-700" fill="none" stroke="currentColor" stroke-width="1.6"><path stroke-linecap="round" stroke-linejoin="round" d="M7 2v9M4 2v5a2 2 0 0 0 2 2h2M20 2c-2.2 0-4 2.5-4 6s1.8 6 4 6M20 2v20M7 11v11" /></svg>
          <svg v-else-if="s.key === 'pickup'" viewBox="0 0 24 24" class="h-[18px] w-[18px] text-brand-700" fill="none" stroke="currentColor" stroke-width="1.6"><path stroke-linecap="round" stroke-linejoin="round" d="M6 8h12l1 12a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2L6 8ZM9 8V6a3 3 0 0 1 6 0v2" /></svg>
          <svg v-else viewBox="0 0 24 24" class="h-[18px] w-[18px] text-brand-700" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="6" cy="18" r="2.5" /><circle cx="18" cy="18" r="2.5" /><path stroke-linecap="round" stroke-linejoin="round" d="M6 18l4-9h5l3 6h-2M10 9l3 3h4" /></svg>
          {{ s.label }}
        </span>
        <span v-if="todayLabel" class="inline-flex items-center gap-2.5">
          <svg viewBox="0 0 24 24" class="h-[18px] w-[18px] text-brand-700" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="12" cy="12" r="9" /><path stroke-linecap="round" stroke-linejoin="round" d="M12 7v5l3.5 2" /></svg>
          Today <span class="text-ink">{{ todayLabel }}</span>
        </span>
      </div>
    </section>

    <!-- Popular dishes -->
    <section v-if="popularItems.length" v-reveal class="mx-auto max-w-6xl px-4 py-20 sm:px-6">
      <div class="flex items-end justify-between gap-4">
        <div>
          <p class="flex items-center gap-3 text-xs font-semibold uppercase tracking-[0.2em] text-brand-700">
            <span class="h-px w-8 bg-brand-300" />Fan favourites
          </p>
          <h2 class="font-display mt-3 text-3xl font-semibold text-brand-900 sm:text-4xl">Popular dishes</h2>
        </div>
        <NuxtLink to="/menu" class="hidden shrink-0 text-sm font-semibold text-brand-700 transition hover:underline sm:inline">View full menu →</NuxtLink>
      </div>

      <div class="mt-10 flex snap-x snap-mandatory gap-5 overflow-x-auto pb-3 sm:grid sm:grid-cols-2 sm:overflow-visible lg:grid-cols-4">
        <NuxtLink
          v-for="item in popularItems" :key="item.id" to="/menu"
          class="group w-64 shrink-0 snap-start overflow-hidden rounded-2xl bg-surface-elevated shadow-sm ring-1 ring-brand-100 transition duration-300 hover:-translate-y-1.5 hover:shadow-2xl hover:ring-brand-200 sm:w-auto"
        >
          <div class="relative aspect-[4/3] overflow-hidden bg-brand-50">
            <img
              v-if="item.image_url" :src="resolveMediaUrl(item.image_url)!" :alt="item.name"
              class="h-full w-full object-cover transition duration-700 group-hover:scale-110"
            >
            <div v-else class="flex h-full items-center justify-center px-4 text-center font-display text-lg text-brand-800/40">{{ item.name }}</div>
            <div class="absolute inset-x-0 bottom-0 h-16 bg-gradient-to-t from-black/40 to-transparent opacity-0 transition duration-300 group-hover:opacity-100" />
          </div>
          <div class="flex items-baseline justify-between gap-3 p-5">
            <p class="font-medium text-ink">{{ item.name }}</p>
            <p class="shrink-0 font-display text-lg font-semibold text-brand-700">{{ formatCurrency(Number(item.price)) }}</p>
          </div>
        </NuxtLink>
      </div>
      <NuxtLink to="/menu" class="mt-8 block text-center text-sm font-semibold text-brand-700 hover:underline sm:hidden">View full menu →</NuxtLink>
    </section>

    <!-- About -->
    <section v-if="current?.about_text" v-reveal class="border-y border-brand-100 bg-surface-muted/50">
      <div class="mx-auto max-w-3xl px-4 py-20 text-center sm:px-6">
        <p class="flex items-center justify-center gap-3 text-xs font-semibold uppercase tracking-[0.2em] text-brand-700">
          <span class="h-px w-8 bg-brand-300" />Our story<span class="h-px w-8 bg-brand-300" />
        </p>
        <h2 class="font-display mt-3 text-3xl font-semibold text-brand-900 sm:text-4xl">About us</h2>
        <p class="font-display mt-7 whitespace-pre-line text-xl font-light leading-relaxed text-ink-muted sm:text-2xl">{{ current.about_text }}</p>
      </div>
    </section>

    <!-- Reviews -->
    <section v-if="reviewsEnabled && reviews.length" v-reveal class="mx-auto max-w-6xl px-4 py-20 sm:px-6">
      <div class="flex flex-col items-center gap-3 text-center">
        <p class="flex items-center gap-3 text-xs font-semibold uppercase tracking-[0.2em] text-brand-700">
          <span class="h-px w-8 bg-brand-300" />What guests say<span class="h-px w-8 bg-brand-300" />
        </p>
        <h2 class="font-display text-3xl font-semibold text-brand-900 sm:text-4xl">Reviews</h2>
        <div v-if="averageRating" class="mt-1 flex items-center gap-2 text-sm text-ink-muted">
          <span class="flex text-amber-500">
            <svg v-for="n in 5" :key="n" viewBox="0 0 20 20" class="h-4 w-4" :fill="n <= Math.round(averageRating) ? 'currentColor' : 'none'" stroke="currentColor" stroke-width="1.2">
              <path d="M10 1.5l2.6 5.27 5.82.85-4.21 4.1 1 5.8L10 14.9l-5.21 2.62 1-5.8-4.21-4.1 5.82-.85z" stroke-linejoin="round" />
            </svg>
          </span>
          <span class="font-semibold text-ink">{{ averageRating }}</span> out of 5 · {{ reviewCount }} review{{ reviewCount === 1 ? '' : 's' }}
        </div>
      </div>

      <div class="mt-12 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
        <div
          v-for="review in reviews" :key="review.id"
          class="rounded-2xl border border-brand-100 bg-surface-elevated p-6 shadow-sm transition duration-300 hover:-translate-y-1 hover:shadow-lg"
        >
          <span class="flex text-amber-500">
            <svg v-for="n in 5" :key="n" viewBox="0 0 20 20" class="h-3.5 w-3.5" :fill="n <= review.rating ? 'currentColor' : 'none'" stroke="currentColor" stroke-width="1.2">
              <path d="M10 1.5l2.6 5.27 5.82.85-4.21 4.1 1 5.8L10 14.9l-5.21 2.62 1-5.8-4.21-4.1 5.82-.85z" stroke-linejoin="round" />
            </svg>
          </span>
          <p v-if="review.comment" class="mt-3 text-sm leading-relaxed text-ink">"{{ review.comment }}"</p>
          <p class="mt-4 text-xs font-semibold uppercase tracking-wide text-ink-subtle">{{ review.reviewer_name }}</p>
          <div v-if="review.staff_reply" class="mt-3 rounded-lg bg-brand-50 p-3 text-xs text-ink-muted">
            <p class="font-semibold uppercase tracking-wide text-brand-700">Owner's reply</p>
            <p class="mt-1">{{ review.staff_reply }}</p>
          </div>
        </div>
      </div>
      <NuxtLink v-if="reviewCount > reviews.length" to="/reviews" class="mt-8 block text-center text-sm font-semibold text-brand-700 hover:underline">
        See all {{ reviewCount }} reviews →
      </NuxtLink>
    </section>

    <!-- Visit us: the map fills the band, the details sit on a glass card over it -->
    <section v-if="hasContactSection" v-reveal class="relative isolate overflow-hidden bg-brand-900">
      <!-- Decorative backdrop: not interactive, so scrolling the page never gets caught by the map.
           "Get directions" is the real way in. -->
      <div v-if="mapEmbedUrl" class="pointer-events-none absolute inset-0">
        <iframe
          :src="mapEmbedUrl" title="Map" loading="lazy" tabindex="-1"
          class="h-full w-full opacity-95 grayscale-[0.6] contrast-[1.02] brightness-[1.03]"
        />
      </div>
      <div
        v-else
        class="absolute inset-0 bg-[radial-gradient(ellipse_at_bottom_right,_var(--color-brand-700)_0%,_transparent_60%)]"
        aria-hidden="true"
      />

      <div class="pointer-events-none relative mx-auto flex max-w-6xl items-center px-4 py-20 sm:px-6 sm:py-28">
        <div class="pointer-events-auto w-full max-w-md rounded-[1.75rem] border border-white/50 bg-white/85 p-8 shadow-2xl shadow-black/20 backdrop-blur-2xl sm:p-10">
          <p class="flex items-center gap-3 text-xs font-semibold uppercase tracking-[0.2em] text-brand-700">
            <span class="h-px w-8 bg-brand-300" />Find us
          </p>
          <h2 class="font-display mt-3 text-3xl font-semibold text-brand-900 sm:text-4xl">Visit us</h2>

          <div class="mt-8 space-y-5 text-sm">
            <div v-if="fullAddress || directionsUrl" class="flex gap-3.5">
              <span class="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-brand-50 text-brand-700">
                <svg viewBox="0 0 24 24" class="h-[18px] w-[18px]" fill="none" stroke="currentColor" stroke-width="1.6"><path stroke-linecap="round" stroke-linejoin="round" d="M12 21s7-5.686 7-11a7 7 0 1 0-14 0c0 5.314 7 11 7 11Z" /><circle cx="12" cy="10" r="2.5" /></svg>
              </span>
              <div>
                <p v-if="fullAddress" class="font-medium text-ink">{{ fullAddress }}</p>
                <a v-if="directionsUrl" :href="directionsUrl" target="_blank" rel="noopener" class="mt-0.5 inline-block font-medium text-brand-700 transition hover:underline">Get directions →</a>
              </div>
            </div>

            <div v-if="current?.phone" class="flex items-center gap-3.5">
              <span class="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-brand-50 text-brand-700">
                <svg viewBox="0 0 24 24" class="h-[18px] w-[18px]" fill="none" stroke="currentColor" stroke-width="1.6"><path stroke-linecap="round" stroke-linejoin="round" d="M4 5.5A1.5 1.5 0 0 1 5.5 4h2.2a1 1 0 0 1 .96.73l.9 3a1 1 0 0 1-.34 1.06l-1.4 1.1a12.5 12.5 0 0 0 5.29 5.29l1.1-1.4a1 1 0 0 1 1.06-.34l3 .9a1 1 0 0 1 .73.96v2.2a1.5 1.5 0 0 1-1.5 1.5A14.5 14.5 0 0 1 4 5.5Z" /></svg>
              </span>
              <a :href="`tel:${current.phone}`" class="font-medium text-ink transition hover:text-brand-700">{{ current.phone }}</a>
            </div>

            <div v-if="current?.email" class="flex items-center gap-3.5">
              <span class="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-brand-50 text-brand-700">
                <svg viewBox="0 0 24 24" class="h-[18px] w-[18px]" fill="none" stroke="currentColor" stroke-width="1.6"><rect x="3" y="5" width="18" height="14" rx="2.5" /><path stroke-linecap="round" stroke-linejoin="round" d="m3.5 7 8.5 6 8.5-6" /></svg>
              </span>
              <a :href="`mailto:${current.email}`" class="font-medium text-ink transition hover:text-brand-700">{{ current.email }}</a>
            </div>
          </div>

          <div v-if="weeklyHours.length" class="mt-7 border-t border-brand-100 pt-6">
            <p class="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.15em] text-ink-subtle">
              <svg viewBox="0 0 24 24" class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="12" cy="12" r="9" /><path stroke-linecap="round" stroke-linejoin="round" d="M12 7v5l3.5 2" /></svg>
              Opening hours
            </p>
            <dl class="mt-3 space-y-1 text-sm">
              <div
                v-for="row in weeklyHours" :key="row.day"
                class="flex justify-between gap-6 rounded-md px-2 py-1"
                :class="row.isToday ? 'bg-brand-50 font-semibold text-ink' : 'text-ink-muted'"
              >
                <dt class="capitalize">{{ row.day }}</dt>
                <dd class="tabular-nums">{{ row.label }}</dd>
              </div>
            </dl>
          </div>

          <div v-if="socialLinks.length" class="mt-7 flex flex-wrap gap-2 border-t border-brand-100 pt-6">
            <a
              v-for="s in socialLinks" :key="s.key" :href="s.url" target="_blank" rel="noopener"
              class="inline-flex items-center rounded-full border border-brand-200 px-4 py-1.5 text-xs font-semibold text-brand-800 transition hover:border-brand-400 hover:bg-brand-50"
            >
              {{ s.label }}
            </a>
          </div>
        </div>
      </div>
    </section>

    <!-- Closing call to action -->
    <section v-reveal class="relative overflow-hidden bg-brand-800">
      <div class="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top,_rgba(255,255,255,0.14)_0%,_transparent_60%)]" aria-hidden="true" />
      <div class="relative mx-auto flex max-w-6xl flex-col items-center gap-5 px-4 py-20 text-center sm:px-6">
        <h2 class="font-display text-3xl font-semibold text-white sm:text-4xl">Hungry yet?</h2>
        <p class="max-w-md text-brand-100/90">Order online for pickup or delivery, or book a table and let us take care of the rest.</p>
        <div class="mt-3 flex flex-wrap items-center justify-center gap-3">
          <NuxtLink to="/menu" class="inline-flex items-center justify-center rounded-full bg-white px-7 py-3 text-sm font-semibold text-brand-800 shadow-lg transition duration-300 hover:-translate-y-0.5 hover:shadow-xl">
            Browse menu
          </NuxtLink>
          <NuxtLink
            v-if="current?.dine_in_enabled"
            to="/reserve"
            class="inline-flex items-center rounded-full border border-white/30 bg-white/10 px-7 py-3 text-sm font-semibold text-white backdrop-blur-md transition duration-300 hover:-translate-y-0.5 hover:bg-white/20"
          >
            Book a table
          </NuxtLink>
        </div>
      </div>
    </section>
  </div>
</template>
