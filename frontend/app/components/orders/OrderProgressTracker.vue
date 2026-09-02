<script setup lang="ts">
import type { OrderStatus } from '~/types/order'

const props = defineProps<{
  status: OrderStatus
}>()

const steps: { key: OrderStatus; label: string }[] = [
  { key: 'PENDING', label: 'Pending' },
  { key: 'CONFIRMED', label: 'Confirmed' },
  { key: 'PREPARING', label: 'Preparing' },
  { key: 'READY', label: 'Ready' },
  { key: 'OUT_FOR_DELIVERY', label: 'Out for delivery' },
  { key: 'DELIVERED', label: 'Delivered' },
  { key: 'COMPLETED', label: 'Completed' },
]

const flow = computed(() => {
  if (props.status === 'CANCELLED') return []
  const deliveryFlow = ['PENDING', 'CONFIRMED', 'PREPARING', 'READY', 'OUT_FOR_DELIVERY', 'DELIVERED', 'COMPLETED']
  const pickupFlow = ['PENDING', 'CONFIRMED', 'PREPARING', 'READY', 'COMPLETED']
  const activeFlow = ['OUT_FOR_DELIVERY', 'DELIVERED'].includes(props.status) ? deliveryFlow : pickupFlow
  return steps.filter(step => activeFlow.includes(step.key))
})

const currentIndex = computed(() => flow.value.findIndex(step => step.key === props.status))
</script>

<template>
  <div v-if="status === 'CANCELLED'" class="rounded-xl bg-red-50 px-4 py-3 text-sm font-medium text-red-700">
    This order was cancelled.
  </div>
  <ol v-else class="space-y-0">
    <li
      v-for="(step, index) in flow"
      :key="step.key"
      class="relative flex gap-4 pb-6 last:pb-0"
    >
      <div class="flex flex-col items-center">
        <span
          class="flex h-8 w-8 items-center justify-center rounded-full text-xs font-bold"
          :class="index <= currentIndex ? 'bg-brand-700 text-white' : 'bg-brand-100 text-brand-600'"
        >
          {{ index + 1 }}
        </span>
        <span v-if="index < flow.length - 1" class="mt-1 h-full w-0.5 flex-1 bg-brand-100" />
      </div>
      <div class="pt-1">
        <p class="font-medium" :class="index <= currentIndex ? 'text-brand-900' : 'text-ink-subtle'">
          {{ step.label }}
        </p>
        <p v-if="index === currentIndex" class="text-xs text-brand-600">
          Current status
        </p>
      </div>
    </li>
  </ol>
</template>
