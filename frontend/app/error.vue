<script setup lang="ts">
defineProps<{ error: { statusCode?: number, statusMessage?: string, message?: string } }>()
</script>

<template>
  <main class="mx-auto flex min-h-screen max-w-md flex-col items-center justify-center px-4 text-center">
    <p class="text-sm font-semibold text-brand-700">{{ error.statusCode ?? 'Error' }}</p>
    <h1 class="mt-2 text-2xl font-bold text-ink">{{ error.statusMessage || 'Something went wrong' }}</h1>
    <p class="mt-2 text-ink-muted">Check the address, or ask the restaurant for their ordering link.</p>
  </main>
</template>
