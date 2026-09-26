<script setup lang="ts">
defineProps<{ error: { statusCode?: number, statusMessage?: string, message?: string } }>()

// The tenant may not resolve at all on some errors (e.g. an unknown host), so this falls back to the
// plain DineFlow name — same fallback the default layout's header uses.
const branding = useBranding()
</script>

<template>
  <main class="mx-auto flex min-h-screen max-w-md flex-col items-center justify-center px-4 text-center">
    <NuxtLink to="/" class="font-display text-xl font-semibold tracking-tight text-brand-800">
      <img v-if="branding.logo.value" :src="branding.logo.value" :alt="branding.name.value ?? 'Home'" class="mx-auto h-10 w-auto max-w-[10rem] object-contain">
      <template v-else>{{ branding.name.value ?? 'DineFlow' }}</template>
    </NuxtLink>
    <p class="mt-8 text-sm font-semibold text-brand-700">{{ error.statusCode ?? 'Error' }}</p>
    <h1 class="mt-2 text-2xl font-bold text-ink">{{ error.statusMessage || 'Something went wrong' }}</h1>
    <p class="mt-2 text-ink-muted">Check the address, or ask the restaurant for their ordering link.</p>
    <NuxtLink to="/" class="mt-6 rounded-lg bg-brand-700 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-800">
      Go home
    </NuxtLink>
  </main>
</template>
