<script setup lang="ts">
defineProps<{
  title?: string
  message: string
}>()

defineEmits<{ retry: [] }>()
</script>

<template>
  <div class="rounded-2xl border border-red-200 bg-red-50/60 px-6 py-8 text-center">
    <p class="font-medium text-red-800">{{ title || 'Something went wrong' }}</p>
    <p class="mt-2 text-sm text-red-700">{{ message }}</p>
    <button
      type="button"
      class="mt-4 rounded-lg bg-white px-4 py-2 text-sm font-medium text-red-800 ring-1 ring-red-200 hover:bg-red-50"
      @click="$emit('retry')"
    >
      Try again
    </button>
  </div>
</template>
