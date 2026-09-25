<script setup lang="ts">
defineProps<{ title: string, updated: string }>()
</script>

<template>
  <div class="mx-auto max-w-2xl px-4 py-12 sm:px-6">
    <NuxtLink to="/" class="text-sm font-medium text-brand-700 hover:underline">← Back home</NuxtLink>
    <h1 class="font-display mt-4 text-3xl font-semibold text-brand-900">{{ title }}</h1>
    <p class="mt-1 text-sm text-ink-subtle">Last updated {{ updated }}</p>
    <div class="prose-legal mt-8 space-y-5 text-sm leading-relaxed text-ink">
      <slot />
    </div>
  </div>
</template>

<style scoped>
.prose-legal :deep(h2) {
  margin-top: 1.75rem;
  font-family: var(--font-display, inherit);
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--color-brand-900, #1a1f1c);
}
.prose-legal :deep(ul) {
  list-style: disc;
  padding-left: 1.25rem;
}
.prose-legal :deep(a) {
  color: var(--color-brand-700, #2c6f53);
  text-decoration: underline;
}
</style>
