<script setup lang="ts">
const props = defineProps<{ status: string }>()

const styles: Record<string, string> = {
  PENDING: 'bg-amber-100 text-amber-900',
  CONFIRMED: 'bg-blue-100 text-blue-900',
  PREPARING: 'bg-orange-100 text-orange-900',
  READY: 'bg-emerald-100 text-emerald-900',
  OUT_FOR_DELIVERY: 'bg-violet-100 text-violet-900',
  DELIVERED: 'bg-teal-100 text-teal-900',
  COMPLETED: 'bg-green-100 text-green-900',
  CANCELLED: 'bg-red-100 text-red-900',
  AVAILABLE: 'bg-green-100 text-green-900',
  OCCUPIED: 'bg-red-100 text-red-900',
  RESERVED: 'bg-amber-100 text-amber-900',
  CLEANING: 'bg-slate-100 text-slate-900',
  HELD: 'bg-amber-100 text-amber-900',
  SEATED: 'bg-violet-100 text-violet-900',
  EXPIRED: 'bg-gray-100 text-gray-700',
}

const label = computed(() => props.status.replace(/_/g, ' '))
const colorClass = computed(() => styles[props.status] || 'bg-brand-100 text-brand-900')
</script>

<template>
  <span
    class="inline-flex rounded-full px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wide"
    :class="colorClass"
  >
    {{ label }}
  </span>
</template>
