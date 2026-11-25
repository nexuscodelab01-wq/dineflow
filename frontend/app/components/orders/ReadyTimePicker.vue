<script setup lang="ts">
import type { Order } from '~/types/order'
import { READY_CHOICES, formatMinutes, readyLabel } from '~/utils/readyTime'

/**
 * Where staff tell the customer how long the order will take: a tap on a common wait, or their own number of
 * minutes. Picking again later moves the promise (a busy kitchen). The page does the saving.
 */
const props = defineProps<{ order: Pick<Order, 'order_type' | 'status' | 'estimated_ready_at'>, busy?: boolean, compact?: boolean }>()
const emit = defineEmits<{ pick: [minutes: number] }>()

const custom = ref('')
const label = computed(() => readyLabel(props.order))

function submitCustom() {
  const n = Math.round(Number(custom.value))
  if (!Number.isFinite(n) || n < 1 || n > 480) return
  custom.value = ''
  emit('pick', n)
}
</script>

<template>
  <div data-testid="ready-time">
    <p class="text-xs font-semibold uppercase tracking-wide text-ink-muted">
      {{ order.order_type === 'DELIVERY' ? 'Arrives in' : 'Ready in' }}
      <span v-if="label" class="ml-1 font-medium normal-case tracking-normal text-brand-800">· {{ label }}</span>
    </p>
    <div class="mt-1.5 flex flex-wrap gap-1.5">
      <button
        v-for="m in (compact ? READY_CHOICES.slice(1, 7) : READY_CHOICES)"
        :key="m"
        type="button"
        class="rounded-full border border-brand-200 bg-white px-2.5 py-1 text-xs font-semibold text-brand-800 hover:bg-brand-50 disabled:opacity-50"
        :disabled="busy"
        @click="emit('pick', m)"
      >
        {{ formatMinutes(m) }}
      </button>
      <form class="flex items-center gap-1" @submit.prevent="submitCustom">
        <input
          v-model="custom"
          type="number"
          min="1"
          max="480"
          inputmode="numeric"
          placeholder="min"
          aria-label="Other number of minutes"
          class="w-16 rounded-full border border-brand-200 px-2.5 py-1 text-xs"
        >
        <button type="submit" class="rounded-full bg-brand-700 px-2.5 py-1 text-xs font-semibold text-white disabled:opacity-50" :disabled="busy || !custom">Set</button>
      </form>
    </div>
  </div>
</template>
