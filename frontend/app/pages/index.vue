<script setup lang="ts">
// A restaurant's own home page — the tenant middleware guarantees a restaurant has resolved by the
// time this renders (an unknown address shows the "no restaurant here" error page instead).
const restaurant = useRestaurantStore()
const branding = useBranding()
const { status: openStatus } = useOpeningStatus()
const current = computed(() => restaurant.current)
</script>

<template>
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
      <p v-if="current?.address" class="text-sm text-ink-subtle">
        {{ current.address }}<span v-if="current.city">, {{ current.city }}</span>
      </p>

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
</template>
