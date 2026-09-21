<script setup lang="ts">
import type { Ticket } from '~/utils/kitchen'
import { ageMs, formatTimer, urgency } from '~/utils/kitchen'

/**
 * One ticket on the kitchen screen. The timer and its colour show how long the order has waited; each dish is a
 * big button so it can be bumped with a thumb, and tapping a bumped dish recalls it.
 */
const props = defineProps<{ ticket: Ticket, now: number, busy?: boolean, canComplete?: boolean }>()
const emit = defineEmits<{ bumpItem: [id: number], recallItem: [id: number], bumpAll: [], complete: [] }>()

const order = computed(() => props.ticket.order)
const age = computed(() => ageMs(order.value.created_at, props.now))
const level = computed(() => urgency(age.value))
const done = computed(() => props.ticket.state === 'done')

const frame = computed(() => {
  if (done.value) return 'border-emerald-300 bg-emerald-50/60'
  return { ok: 'border-brand-100 bg-surface-elevated', warn: 'border-amber-400 bg-amber-50', late: 'border-red-500 bg-red-50' }[level.value]
})
const timerClass = computed(() => {
  if (done.value) return 'text-emerald-800'
  return { ok: 'text-ink', warn: 'text-amber-800', late: 'text-red-700' }[level.value]
})

const where = computed(() => {
  const o = order.value
  if (o.order_type === 'DINE_IN') return o.table_number ? `Table ${o.table_number}` : 'Dine-in'
  return o.order_type === 'DELIVERY' ? 'Delivery' : 'Pickup'
})
const openCount = computed(() => props.ticket.items.filter(i => i.status !== 'READY').length)
</script>

<template>
  <article class="rounded-2xl border-2 p-4 shadow-sm" :class="frame" :data-urgency="done ? 'done' : level" data-testid="ticket">
    <header class="flex items-start justify-between gap-3">
      <div>
        <p class="text-2xl font-bold leading-none text-brand-900">{{ where }}</p>
        <p class="mt-1 text-xs text-ink-subtle">{{ order.order_number }} · {{ order.customer_name }}</p>
      </div>
      <p class="font-mono text-2xl font-bold tabular-nums" :class="timerClass" data-testid="timer">{{ formatTimer(age) }}</p>
    </header>

    <ul class="mt-3 space-y-2">
      <li v-for="item in ticket.items" :key="item.id">
        <button
          class="flex w-full items-start gap-3 rounded-xl border px-3 py-2.5 text-left transition"
          :class="item.status === 'READY' ? 'border-emerald-300 bg-emerald-100/70 text-ink-muted' : 'border-brand-200 bg-white hover:bg-brand-50'"
          :disabled="busy"
          :aria-label="item.status === 'READY' ? `Recall ${item.item_name}` : `Bump ${item.item_name}`"
          @click="item.status === 'READY' ? emit('recallItem', item.id) : emit('bumpItem', item.id)"
        >
          <span class="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md border-2 text-lg font-bold" :class="item.status === 'READY' ? 'border-emerald-600 bg-emerald-600 text-white' : 'border-brand-300 text-transparent'" aria-hidden="true">✓</span>
          <span class="min-w-0 flex-1" :class="item.status === 'READY' ? 'line-through decoration-2' : ''">
            <span class="block text-lg font-semibold text-ink"><span class="mr-1 font-bold text-brand-800">{{ item.quantity }}×</span>{{ item.item_name }}</span>
            <span v-for="mod in item.modifiers" :key="mod.id" class="block text-sm font-semibold text-ink">+ {{ mod.option_name }}</span>
            <span v-if="item.special_instructions" class="mt-1 block rounded-md border border-amber-300 bg-amber-100 px-2 py-1 text-sm font-bold text-amber-950" data-testid="special-instructions">
              <span class="mr-1 uppercase tracking-wide">Note:</span>{{ item.special_instructions }}
            </span>
          </span>
          <span v-if="item.station && item.station !== 'KITCHEN'" class="shrink-0 rounded-full bg-brand-100 px-2 py-0.5 text-xs font-semibold text-brand-900">{{ item.station }}</span>
        </button>
      </li>
    </ul>

    <p v-if="order.notes" class="mt-3 rounded-md border border-amber-300 bg-amber-100 px-2 py-1 text-sm font-bold text-amber-950" data-testid="order-note">
      <span class="mr-1 uppercase tracking-wide">Order note:</span>{{ order.notes }}
    </p>

    <footer class="mt-3 flex gap-2">
      <AppButton v-if="!done" class="flex-1 py-3 text-base" :disabled="busy" @click="emit('bumpAll')">Bump all ({{ openCount }})</AppButton>
      <AppButton v-if="canComplete && done" class="flex-1 py-3 text-base" :disabled="busy" @click="emit('complete')">Served — clear</AppButton>
    </footer>
  </article>
</template>
