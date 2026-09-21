<script setup lang="ts">
import type { OrderItem } from '~/types/order'
import { formatCurrency } from '~/utils/format'

/**
 * The lines of an order, with everything the cook or guest needs: options chosen
 * (Large, Extra cheese…) and the guest's special instructions.
 *
 * `kitchen` is built for a glance across a busy pass: large type, options in bold, and special
 * instructions in a loud callout so they are never missed.
 */
withDefaults(defineProps<{
  items: OrderItem[]
  variant?: 'kitchen' | 'default'
  showPrices?: boolean
}>(), {
  variant: 'default',
  showPrices: false,
})
</script>

<template>
  <ul :class="variant === 'kitchen' ? 'space-y-3' : 'space-y-3 text-sm'">
    <li
      v-for="item in items"
      :key="item.id"
      class="flex items-start justify-between gap-3"
    >
      <div class="min-w-0">
        <p :class="variant === 'kitchen' ? 'text-base font-semibold text-ink' : 'font-medium text-ink'">
          <span :class="variant === 'kitchen' ? 'mr-1 text-lg font-bold text-brand-800' : ''">{{ item.quantity }}×</span>
          {{ item.item_name }}
        </p>

        <ul v-if="item.modifiers?.length" class="mt-0.5" :class="variant === 'kitchen' ? 'text-sm font-semibold text-ink' : 'text-ink-muted'">
          <li v-for="mod in item.modifiers" :key="mod.id">
            <template v-if="variant === 'kitchen'">+ {{ mod.option_name }}</template>
            <template v-else>{{ mod.modifier_name }}: {{ mod.option_name }}</template>
          </li>
        </ul>

        <p
          v-if="item.special_instructions"
          class="mt-1.5 rounded-md border border-amber-300 bg-amber-100 px-2 py-1 font-semibold text-amber-950"
          :class="variant === 'kitchen' ? 'text-sm' : 'text-xs'"
          data-testid="special-instructions"
        >
          <span class="mr-1 uppercase tracking-wide">Note:</span>{{ item.special_instructions }}
        </p>
      </div>
      <span v-if="showPrices" class="shrink-0 text-sm">{{ formatCurrency(Number(item.line_total)) }}</span>
    </li>
  </ul>
</template>
