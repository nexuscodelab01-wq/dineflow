<script setup lang="ts">
// A restaurant's own home page — the tenant middleware guarantees a restaurant has resolved by the
// time this renders (an unknown address shows the "no restaurant here" error page instead).
import type { MenuItem } from '~/types/menu'
import { fetchMenu } from '~/services/menu'
import { resolveMediaUrl } from '~/utils/media'
import { formatCurrency } from '~/utils/format'
import { wallClockIn } from '~/utils/timezone'
import { weeklyHoursLabels } from '~/utils/hours'

const restaurant = useRestaurantStore()
const branding = useBranding()
const { status: openStatus, todayLabel } = useOpeningStatus()
const current = computed(() => restaurant.current)

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

const heroSlides = computed(() => (current.value?.gallery ?? []).slice(0, 5))
const heroIndex = ref(0)
let heroTimer: ReturnType<typeof setInterval> | undefined
onMounted(() => {
  if (heroSlides.value.length > 1) {
    heroTimer = setInterval(() => { heroIndex.value = (heroIndex.value + 1) % heroSlides.value.length }, 6000)
  }
})
onUnmounted(() => { if (heroTimer) clearInterval(heroTimer) })

// ---- gallery lightbox -------------------------------------------------------------------------

const lightboxIndex = ref<number | null>(null)
const gallery = computed(() => current.value?.gallery ?? [])
function openLightbox(i: number) { lightboxIndex.value = i }
function closeLightbox() { lightboxIndex.value = null }
function nextImage() { if (lightboxIndex.value != null) lightboxIndex.value = (lightboxIndex.value + 1) % gallery.value.length }
function prevImage() { if (lightboxIndex.value != null) lightboxIndex.value = (lightboxIndex.value - 1 + gallery.value.length) % gallery.value.length }
function onLightboxKey(e: KeyboardEvent) {
  if (e.key === 'Escape') closeLightbox()
  else if (e.key === 'ArrowRight') nextImage()
  else if (e.key === 'ArrowLeft') prevImage()
}
watch(lightboxIndex, (open) => {
  if (typeof window === 'undefined') return
  if (open != null) window.addEventListener('keydown', onLightboxKey)
  else window.removeEventListener('keydown', onLightboxKey)
})
onUnmounted(() => { if (typeof window !== 'undefined') window.removeEventListener('keydown', onLightboxKey) })
</script>

<template>
  <div>
    <section class="relative overflow-hidden">
      <template v-if="heroSlides.length">
        <div class="absolute inset-0">
          <img
            v-for="(url, i) in heroSlides" :key="url"
            :src="resolveMediaUrl(url)!" alt=""
            class="absolute inset-0 h-full w-full animate-ken-burns object-cover transition-opacity duration-[1500ms]"
            :class="i === heroIndex ? 'opacity-100' : 'opacity-0'"
          >
          <div class="absolute inset-0 bg-gradient-to-t from-black/70 via-black/30 to-black/10" aria-hidden="true" />
        </div>
        <div v-if="heroSlides.length > 1" class="absolute bottom-6 left-1/2 z-10 flex -translate-x-1/2 gap-1.5">
          <button
            v-for="(url, i) in heroSlides" :key="url" type="button"
            class="h-1.5 rounded-full transition-all" :class="i === heroIndex ? 'w-6 bg-white' : 'w-1.5 bg-white/50 hover:bg-white/80'"
            :aria-label="`Show photo ${i + 1}`" @click="heroIndex = i"
          />
        </div>
      </template>
      <div
        v-else
        class="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,_var(--color-brand-100)_0%,_transparent_55%),radial-gradient(ellipse_at_bottom_left,_var(--color-brand-50)_0%,_transparent_50%)]"
        aria-hidden="true"
      />

      <div class="relative mx-auto flex max-w-6xl flex-col items-start gap-6 px-4 py-24 sm:px-6 sm:py-32" :class="heroSlides.length ? 'text-white' : ''">
        <img v-if="branding.logo.value" :src="branding.logo.value" :alt="current?.name" class="h-16 w-auto max-w-[16rem] rounded-lg bg-white/90 object-contain p-1.5 sm:h-20">

        <p
          v-if="current?.opening_hours"
          class="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold"
          :class="openStatus.open ? 'bg-emerald-100 text-emerald-900' : 'bg-amber-100 text-amber-900'"
        >
          <span class="h-2 w-2 rounded-full" :class="openStatus.open ? 'bg-emerald-500' : 'bg-amber-500'" />
          {{ openStatus.open ? 'Open now' : 'Closed now' }}
        </p>

        <h1
          class="font-display max-w-2xl text-4xl font-semibold leading-tight sm:text-5xl md:text-6xl"
          :class="heroSlides.length ? 'text-white drop-shadow-sm' : 'text-brand-900'"
        >
          {{ current?.name ?? 'Welcome' }}
        </h1>
        <p class="max-w-xl text-lg leading-relaxed" :class="heroSlides.length ? 'text-white/90' : 'text-ink-muted'">
          {{ current?.description || 'Order online, or book a table — we\'d love to have you.' }}
        </p>
        <p v-if="fullAddress" class="text-sm" :class="heroSlides.length ? 'text-white/75' : 'text-ink-subtle'">{{ fullAddress }}</p>

        <div class="flex flex-wrap items-center gap-3 pt-2">
          <NuxtLink
            to="/menu"
            class="inline-flex items-center justify-center rounded-lg bg-brand-700 px-5 py-2.5 text-sm font-semibold text-white shadow-lg shadow-brand-900/20 transition hover:bg-brand-800 hover:shadow-xl"
          >
            Browse menu
          </NuxtLink>
          <NuxtLink
            v-if="current?.dine_in_enabled"
            to="/reserve"
            class="inline-flex items-center rounded-lg border px-5 py-2.5 text-sm font-semibold transition"
            :class="heroSlides.length ? 'border-white/40 bg-white/10 text-white backdrop-blur-sm hover:bg-white/20' : 'border-brand-200 bg-surface-elevated text-ink hover:bg-brand-50'"
          >
            Book a table
          </NuxtLink>
        </div>
      </div>
    </section>

    <section v-if="serviceHighlights.length || todayLabel" class="border-b border-brand-100 bg-surface-elevated">
      <div class="mx-auto flex max-w-6xl flex-wrap items-center justify-center gap-x-10 gap-y-3 px-4 py-5 text-sm font-medium text-ink-muted sm:px-6">
        <span v-for="s in serviceHighlights" :key="s.key" class="inline-flex items-center gap-2">
          <svg v-if="s.key === 'dine-in'" viewBox="0 0 24 24" class="h-4 w-4 text-brand-700" fill="none" stroke="currentColor" stroke-width="1.75"><path stroke-linecap="round" stroke-linejoin="round" d="M7 2v9M4 2v5a2 2 0 0 0 2 2h2M20 2c-2.2 0-4 2.5-4 6s1.8 6 4 6M20 2v20M7 11v11" /></svg>
          <svg v-else-if="s.key === 'pickup'" viewBox="0 0 24 24" class="h-4 w-4 text-brand-700" fill="none" stroke="currentColor" stroke-width="1.75"><path stroke-linecap="round" stroke-linejoin="round" d="M6 8h12l1 12a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2L6 8ZM9 8V6a3 3 0 0 1 6 0v2" /></svg>
          <svg v-else viewBox="0 0 24 24" class="h-4 w-4 text-brand-700" fill="none" stroke="currentColor" stroke-width="1.75"><circle cx="6" cy="18" r="2.5" /><circle cx="18" cy="18" r="2.5" /><path stroke-linecap="round" stroke-linejoin="round" d="M6 18l4-9h5l3 6h-2M10 9l3 3h4" /></svg>
          {{ s.label }}
        </span>
        <span v-if="todayLabel" class="inline-flex items-center gap-2">
          <svg viewBox="0 0 24 24" class="h-4 w-4 text-brand-700" fill="none" stroke="currentColor" stroke-width="1.75"><circle cx="12" cy="12" r="9" /><path stroke-linecap="round" stroke-linejoin="round" d="M12 7v5l3.5 2" /></svg>
          Today: {{ todayLabel }}
        </span>
      </div>
    </section>

    <section v-if="popularItems.length" v-reveal class="mx-auto max-w-6xl px-4 py-16 sm:px-6">
      <div class="flex items-end justify-between gap-4">
        <div>
          <p class="text-xs font-semibold uppercase tracking-widest text-brand-700">Fan favourites</p>
          <h2 class="font-display mt-1 text-2xl font-semibold text-brand-900 sm:text-3xl">Popular dishes</h2>
        </div>
        <NuxtLink to="/menu" class="hidden shrink-0 text-sm font-semibold text-brand-700 hover:underline sm:inline">View full menu →</NuxtLink>
      </div>
      <div class="mt-8 flex snap-x snap-mandatory gap-4 overflow-x-auto pb-2 sm:grid sm:grid-cols-2 sm:overflow-visible lg:grid-cols-4">
        <NuxtLink
          v-for="item in popularItems" :key="item.id" to="/menu"
          class="group w-64 shrink-0 snap-start overflow-hidden rounded-2xl border border-brand-100 bg-surface-elevated transition hover:-translate-y-1 hover:shadow-lg sm:w-auto"
        >
          <div class="aspect-[4/3] overflow-hidden bg-brand-50">
            <img
              v-if="item.image_url" :src="resolveMediaUrl(item.image_url)!" :alt="item.name"
              class="h-full w-full object-cover transition duration-500 group-hover:scale-110"
            >
            <div v-else class="flex h-full items-center justify-center text-sm text-ink-subtle">{{ item.name }}</div>
          </div>
          <div class="p-4">
            <p class="font-medium text-ink">{{ item.name }}</p>
            <p class="mt-1 text-sm font-semibold text-brand-700">{{ formatCurrency(Number(item.price)) }}</p>
          </div>
        </NuxtLink>
      </div>
      <NuxtLink to="/menu" class="mt-6 block text-center text-sm font-semibold text-brand-700 hover:underline sm:hidden">View full menu →</NuxtLink>
    </section>

    <section v-if="gallery.length" v-reveal class="border-t border-brand-100 bg-surface-muted/40">
      <div class="mx-auto max-w-6xl px-4 py-16 sm:px-6">
        <p class="text-xs font-semibold uppercase tracking-widest text-brand-700">A closer look</p>
        <h2 class="font-display mt-1 text-2xl font-semibold text-brand-900 sm:text-3xl">Gallery</h2>
        <div class="mt-8 grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
          <button
            v-for="(url, i) in gallery" :key="url" type="button"
            class="group aspect-square overflow-hidden rounded-xl focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-600"
            :aria-label="`Open photo ${i + 1}`"
            @click="openLightbox(i)"
          >
            <img :src="resolveMediaUrl(url)!" alt="" loading="lazy" class="h-full w-full object-cover transition duration-500 group-hover:scale-110">
          </button>
        </div>
      </div>
    </section>

    <section v-if="current?.about_text" v-reveal class="border-t border-brand-100">
      <div class="mx-auto max-w-3xl px-4 py-16 text-center sm:px-6">
        <p class="text-xs font-semibold uppercase tracking-widest text-brand-700">Our story</p>
        <h2 class="font-display mt-1 text-2xl font-semibold text-brand-900 sm:text-3xl">About us</h2>
        <p class="mt-5 whitespace-pre-line text-lg leading-relaxed text-ink-muted">{{ current.about_text }}</p>
      </div>
    </section>

    <section v-if="hasContactSection" v-reveal class="border-t border-brand-100 bg-surface-muted/40">
      <div class="mx-auto grid max-w-6xl gap-10 px-4 py-16 sm:px-6 md:grid-cols-2">
        <div>
          <p class="text-xs font-semibold uppercase tracking-widest text-brand-700">Find us</p>
          <h2 class="font-display mt-1 text-2xl font-semibold text-brand-900 sm:text-3xl">Visit us</h2>
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
            <div v-if="weeklyHours.length">
              <dt class="font-semibold text-ink">Hours</dt>
              <dd class="mt-1.5 space-y-0.5">
                <div v-for="row in weeklyHours" :key="row.day" class="flex justify-between gap-6" :class="row.isToday ? 'font-semibold text-ink' : 'text-ink-muted'">
                  <span class="capitalize">{{ row.day }}</span>
                  <span>{{ row.label }}</span>
                </div>
              </dd>
            </div>
          </dl>
        </div>

        <iframe
          v-if="mapEmbedUrl"
          :src="mapEmbedUrl"
          title="Map"
          loading="lazy"
          class="h-64 w-full rounded-xl border border-brand-100 shadow-sm md:h-full"
        />
        <div v-else-if="fullAddress" class="flex h-64 items-center justify-center rounded-xl border border-brand-100 bg-surface-elevated text-center text-sm text-ink-subtle md:h-full">
          <div class="px-6">
            <p>{{ fullAddress }}</p>
            <a v-if="directionsUrl" :href="directionsUrl" target="_blank" rel="noopener" class="mt-2 inline-block font-medium text-brand-700 underline">Get directions</a>
          </div>
        </div>
      </div>
    </section>

    <section v-reveal class="border-t border-brand-100 bg-brand-800">
      <div class="mx-auto flex max-w-6xl flex-col items-center gap-4 px-4 py-14 text-center sm:px-6">
        <h2 class="font-display text-2xl font-semibold text-white sm:text-3xl">Hungry yet?</h2>
        <p class="max-w-md text-brand-100">Order online for pickup or delivery, or book a table and let us take care of the rest.</p>
        <div class="mt-2 flex flex-wrap items-center justify-center gap-3">
          <NuxtLink to="/menu" class="inline-flex items-center justify-center rounded-lg bg-white px-5 py-2.5 text-sm font-semibold text-brand-800 shadow-lg transition hover:bg-brand-50">
            Browse menu
          </NuxtLink>
          <NuxtLink
            v-if="current?.dine_in_enabled"
            to="/reserve"
            class="inline-flex items-center rounded-lg border border-white/40 bg-white/10 px-5 py-2.5 text-sm font-semibold text-white backdrop-blur-sm transition hover:bg-white/20"
          >
            Book a table
          </NuxtLink>
        </div>
      </div>
    </section>

    <Teleport to="body">
      <div
        v-if="lightboxIndex != null"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/90 p-4 animate-cross-fade"
        role="dialog" aria-modal="true" aria-label="Photo"
        @click.self="closeLightbox"
      >
        <button type="button" class="absolute right-4 top-4 rounded-full bg-white/10 p-2 text-white hover:bg-white/20" aria-label="Close" @click="closeLightbox">
          <svg viewBox="0 0 24 24" class="h-6 w-6" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" d="M6 6l12 12M18 6L6 18" /></svg>
        </button>
        <button
          v-if="gallery.length > 1" type="button"
          class="absolute left-2 top-1/2 -translate-y-1/2 rounded-full bg-white/10 p-2 text-white hover:bg-white/20 sm:left-4"
          aria-label="Previous photo" @click="prevImage"
        >
          <svg viewBox="0 0 24 24" class="h-6 w-6" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M15 6l-6 6 6 6" /></svg>
        </button>
        <img :src="resolveMediaUrl(gallery[lightboxIndex])!" alt="" class="max-h-[85vh] max-w-[90vw] rounded-lg object-contain shadow-2xl">
        <button
          v-if="gallery.length > 1" type="button"
          class="absolute right-2 top-1/2 -translate-y-1/2 rounded-full bg-white/10 p-2 text-white hover:bg-white/20 sm:right-4"
          aria-label="Next photo" @click="nextImage"
        >
          <svg viewBox="0 0 24 24" class="h-6 w-6" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M9 6l6 6-6 6" /></svg>
        </button>
      </div>
    </Teleport>
  </div>
</template>
