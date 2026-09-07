<script setup lang="ts">
defineProps<{
  title: string
  description?: string
}>()
</script>

<template>
  <div class="rounded-2xl border border-dashed border-brand-200 bg-surface-elevated/50 px-6 py-16 text-center">
    <p class="font-medium text-ink">{{ title }}</p>
    <p v-if="description" class="mt-2 text-sm text-ink-muted">{{ description }}</p>
    <div v-if="$slots.default" class="mt-4">
      <slot />
    </div>
  </div>
</template>
