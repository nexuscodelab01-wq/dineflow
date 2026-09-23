<script setup lang="ts">
// The full photo gallery, linked from the home page hero. Kept off the home page itself so the
// hero slideshow stays the single visual story there.
import { resolveMediaUrl } from '~/utils/media'

const restaurant = useRestaurantStore()
const current = computed(() => restaurant.current)
const gallery = computed(() => current.value?.gallery ?? [])

useHead({ title: 'Gallery' })

const lightboxIndex = ref<number | null>(null)
function openLightbox(i: number) { lightboxIndex.value = i }
function closeLightbox() { lightboxIndex.value = null }
function nextImage() { if (lightboxIndex.value != null) lightboxIndex.value = (lightboxIndex.value + 1) % gallery.value.length }
function prevImage() { if (lightboxIndex.value != null) lightboxIndex.value = (lightboxIndex.value - 1 + gallery.value.length) % gallery.value.length }

function onKey(e: KeyboardEvent) {
  if (lightboxIndex.value == null) return
  if (e.key === 'Escape') closeLightbox()
  else if (e.key === 'ArrowRight') nextImage()
  else if (e.key === 'ArrowLeft') prevImage()
}
onMounted(() => window.addEventListener('keydown', onKey))
onUnmounted(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <div class="mx-auto max-w-6xl px-4 py-16 sm:px-6 sm:py-20">
    <div class="flex flex-wrap items-end justify-between gap-4">
      <div>
        <p class="text-xs font-semibold uppercase tracking-[0.2em] text-brand-700">A closer look</p>
        <h1 class="font-display mt-2 text-4xl font-semibold text-brand-900 sm:text-5xl">Gallery</h1>
        <p v-if="current?.name" class="mt-3 text-ink-muted">Inside {{ current.name }}</p>
      </div>
      <NuxtLink to="/" class="text-sm font-semibold text-brand-700 transition hover:underline">← Back home</NuxtLink>
    </div>

    <!-- Editorial grid: every seventh photo takes a 2×2 tile so the wall never reads as a plain
         contact sheet, and it still fills neatly whether there are 3 photos or 20. -->
    <div v-if="gallery.length" class="mt-12 grid grid-cols-2 gap-4 md:grid-cols-3">
      <button
        v-for="(url, i) in gallery" :key="url"
        type="button"
        class="group relative aspect-square overflow-hidden rounded-2xl bg-brand-50 shadow-sm transition duration-300 hover:shadow-2xl focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-600"
        :class="i % 7 === 0 ? 'md:col-span-2 md:row-span-2' : ''"
        :aria-label="`Open photo ${i + 1}`"
        @click="openLightbox(i)"
      >
        <img :src="resolveMediaUrl(url)!" alt="" loading="lazy" class="h-full w-full object-cover transition duration-700 group-hover:scale-105">
        <span class="absolute inset-0 bg-gradient-to-t from-black/30 to-transparent opacity-0 transition duration-300 group-hover:opacity-100" />
      </button>
    </div>

    <EmptyState
      v-else
      class="mt-12"
      title="No photos yet"
      description="This restaurant hasn't added any photos to its gallery."
    />

    <Teleport to="body">
      <div
        v-if="lightboxIndex != null"
        class="animate-cross-fade fixed inset-0 z-50 flex items-center justify-center bg-black/95 p-4 backdrop-blur-sm"
        role="dialog" aria-modal="true" aria-label="Photo"
        @click.self="closeLightbox"
      >
        <button type="button" class="absolute right-4 top-4 rounded-full bg-white/10 p-2.5 text-white transition hover:bg-white/20" aria-label="Close" @click="closeLightbox">
          <svg viewBox="0 0 24 24" class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" d="M6 6l12 12M18 6L6 18" /></svg>
        </button>
        <button
          v-if="gallery.length > 1" type="button"
          class="absolute left-2 top-1/2 -translate-y-1/2 rounded-full bg-white/10 p-2.5 text-white transition hover:bg-white/20 sm:left-6"
          aria-label="Previous photo" @click="prevImage"
        >
          <svg viewBox="0 0 24 24" class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M15 6l-6 6 6 6" /></svg>
        </button>
        <figure class="flex max-h-full flex-col items-center gap-3">
          <img :src="resolveMediaUrl(gallery[lightboxIndex])!" alt="" class="max-h-[82vh] max-w-[90vw] rounded-xl object-contain shadow-2xl">
          <figcaption class="text-xs tracking-widest text-white/60">{{ lightboxIndex + 1 }} / {{ gallery.length }}</figcaption>
        </figure>
        <button
          v-if="gallery.length > 1" type="button"
          class="absolute right-2 top-1/2 -translate-y-1/2 rounded-full bg-white/10 p-2.5 text-white transition hover:bg-white/20 sm:right-6"
          aria-label="Next photo" @click="nextImage"
        >
          <svg viewBox="0 0 24 24" class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M9 6l6 6-6 6" /></svg>
        </button>
      </div>
    </Teleport>
  </div>
</template>
