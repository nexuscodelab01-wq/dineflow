<script setup lang="ts">
import type { DateRangePreset } from '~/types/analytics'
import { DATE_RANGE_OPTIONS } from '~/types/analytics'

const preset = defineModel<DateRangePreset>('preset', { default: 'last_7_days' })
const startDate = defineModel<string>('startDate', { default: '' })
const endDate = defineModel<string>('endDate', { default: '' })

defineEmits<{ change: [] }>()
</script>

<template>
  <div class="flex flex-wrap items-end gap-3">
    <div>
      <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-ink-subtle">Period</label>
      <select
        v-model="preset"
        class="rounded-lg border border-brand-200 bg-white px-3 py-2 text-sm"
        @change="$emit('change')"
      >
        <option v-for="opt in DATE_RANGE_OPTIONS" :key="opt.value" :value="opt.value">
          {{ opt.label }}
        </option>
      </select>
    </div>
    <template v-if="preset === 'custom'">
      <div>
        <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-ink-subtle">From</label>
        <input v-model="startDate" type="date" class="rounded-lg border border-brand-200 px-3 py-2 text-sm" @change="$emit('change')">
      </div>
      <div>
        <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-ink-subtle">To</label>
        <input v-model="endDate" type="date" class="rounded-lg border border-brand-200 px-3 py-2 text-sm" @change="$emit('change')">
      </div>
    </template>
  </div>
</template>
