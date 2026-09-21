<script setup lang="ts">
// A stripped-down frame for guests at a table: the restaurant's identity and nothing else to tap away to.
const branding = useBranding()
</script>

<template>
  <div class="flex min-h-screen flex-col bg-surface text-ink">
    <header class="border-b border-brand-100 bg-surface-elevated">
      <div class="mx-auto flex max-w-2xl items-center gap-3 px-4 py-3">
        <img v-if="branding.logo.value" :src="branding.logo.value" :alt="branding.name.value ?? ''" class="h-8 w-auto max-w-[9rem] object-contain">
        <span v-else class="font-display text-lg font-semibold text-brand-800">{{ branding.name.value ?? 'DineFlow' }}</span>
      </div>
    </header>
    <slot />
  </div>
</template>
