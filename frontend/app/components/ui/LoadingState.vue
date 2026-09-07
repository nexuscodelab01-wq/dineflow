<script setup lang="ts">
withDefaults(defineProps<{
  rows?: number
  heightClass?: string
}>(), {
  rows: 3,
  heightClass: 'h-40',
})
</script>

<template>
  <div class="space-y-3" role="status" aria-label="Loading">
    <div
      v-for="n in rows"
      :key="n"
      class="animate-pulse rounded-2xl bg-brand-100/60"
      :class="heightClass"
    />
  </div>
</template>
