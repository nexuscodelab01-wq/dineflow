<script setup lang="ts">
import type { MenuItemDetail } from '~/types/menu'
import { formatCurrency } from '~/utils/format'
import { addLine, changeQuantity, lineCount, subtotal, type TableLine } from '~/utils/table-cart'

/**
 * A waiter picks dishes for a table and sends them to the kitchen as one round. Dishes with options
 * (size, extras…) open a small panel; everything else is one tap.
 */
const props = defineProps<{ items: MenuItemDetail[], tableNumber: string, sending?: boolean }>()
const emit = defineEmits<{ send: [lines: TableLine[], notes: string], close: [] }>()

const search = ref('')
const lines = ref<TableLine[]>([])
const notes = ref('')
const open = ref<MenuItemDetail | null>(null)
const options = ref<Record<number, number[]>>({})
const note = ref('')
const qty = ref(1)
const error = ref('')

const shown = computed(() => {
  const q = search.value.trim().toLowerCase()
  return props.items.filter(i => i.is_available && (!q || i.name.toLowerCase().includes(q) || (i.category_name ?? '').toLowerCase().includes(q)))
})

const needsPanel = (item: MenuItemDetail) => item.modifiers.length > 0

function choose(item: MenuItemDetail) {
  error.value = ''
  if (!needsPanel(item)) {
    lines.value = addLine(lines.value, { menuItemId: item.id, name: item.name, unitPrice: Number(item.price), quantity: 1, optionIds: [], optionNames: [] })
    return
  }
  open.value = item
  qty.value = 1
  note.value = ''
  options.value = {}
  for (const m of item.modifiers) {
    const defaults = m.options.filter(o => o.is_default).map(o => o.id)
    options.value[m.id] = m.max_selections === 1 ? [defaults[0] ?? (m.is_required ? m.options[0]?.id : undefined)].filter(Boolean) as number[] : defaults
  }
}

function toggle(modifierId: number, optionId: number, max: number) {
  const current = options.value[modifierId] ?? []
  if (max === 1) options.value[modifierId] = [optionId]
  else if (current.includes(optionId)) options.value[modifierId] = current.filter(id => id !== optionId)
  else if (current.length < max) options.value[modifierId] = [...current, optionId]
}

function addConfigured() {
  const item = open.value
  if (!item) return
  for (const m of item.modifiers) {
    if (m.is_required && (options.value[m.id] ?? []).length < Math.max(m.min_selections, 1)) {
      error.value = `Choose ${m.name}`
      return
    }
  }
  const ids = Object.values(options.value).flat()
  const picked = item.modifiers.flatMap(m => m.options.filter(o => ids.includes(o.id)))
  lines.value = addLine(lines.value, {
    menuItemId: item.id, name: item.name, unitPrice: Number(item.price) + picked.reduce((n, o) => n + Number(o.price_adjustment), 0),
    quantity: qty.value, optionIds: ids, optionNames: picked.map(o => o.name), instructions: note.value || undefined,
  })
  open.value = null
}
</script>

<template>
  <div class="fixed inset-0 z-40 flex items-end justify-center bg-black/40 sm:items-center" role="dialog" aria-modal="true" :aria-label="`Add items for table ${tableNumber}`" @click.self="emit('close')">
    <div class="flex max-h-[92vh] w-full max-w-2xl flex-col overflow-hidden rounded-t-2xl bg-surface-elevated sm:rounded-2xl">
      <header class="flex items-center justify-between gap-3 border-b border-brand-100 p-4">
        <h2 class="font-display text-xl font-semibold text-brand-900">Add items · Table {{ tableNumber }}</h2>
        <button class="text-2xl leading-none text-ink-muted" aria-label="Close" @click="emit('close')">×</button>
      </header>

      <div class="overflow-y-auto p-4">
        <input v-model="search" type="search" placeholder="Search the menu…" class="w-full rounded-lg border border-brand-200 px-3 py-2.5 text-base">

        <ul class="mt-3 divide-y divide-brand-100">
          <li v-for="item in shown" :key="item.id">
            <button class="flex w-full items-center justify-between gap-3 py-3 text-left" @click="choose(item)">
              <span>
                <span class="block font-semibold">{{ item.name }}</span>
                <span class="block text-xs text-ink-subtle">{{ item.category_name }}<span v-if="needsPanel(item)"> · has options</span></span>
              </span>
              <span class="flex items-center gap-3">
                <span class="text-sm font-semibold text-brand-800">{{ formatCurrency(Number(item.price)) }}</span>
                <span class="flex h-8 w-8 items-center justify-center rounded-full bg-brand-700 text-lg text-white" aria-hidden="true">+</span>
              </span>
            </button>
          </li>
          <li v-if="!shown.length" class="py-6 text-center text-sm text-ink-muted">No dishes match.</li>
        </ul>
      </div>

      <footer class="border-t border-brand-100 p-4">
        <ul v-if="lines.length" class="mb-3 max-h-32 space-y-1 overflow-y-auto text-sm">
          <li v-for="l in lines" :key="l.key" class="flex items-center justify-between gap-2">
            <span class="min-w-0 truncate"><strong>{{ l.quantity }}×</strong> {{ l.name }}<span v-if="l.optionNames.length" class="text-ink-muted"> ({{ l.optionNames.join(', ') }})</span><span v-if="l.instructions" class="text-ink-muted"> — {{ l.instructions }}</span></span>
            <span class="flex shrink-0 gap-1">
              <button class="h-7 w-7 rounded-full border border-brand-200" aria-label="Fewer" @click="lines = changeQuantity(lines, l.key, -1)">−</button>
              <button class="h-7 w-7 rounded-full border border-brand-200" aria-label="More" @click="lines = changeQuantity(lines, l.key, 1)">+</button>
            </span>
          </li>
        </ul>
        <input v-model="notes" type="text" maxlength="200" placeholder="Note for the kitchen (optional)" class="mb-3 w-full rounded-lg border border-brand-200 px-3 py-2 text-sm">
        <AppButton class="w-full py-3 text-base" :disabled="!lines.length || sending" @click="emit('send', lines, notes)">
          {{ sending ? 'Sending…' : lines.length ? `Send to kitchen · ${lineCount(lines)} item${lineCount(lines) === 1 ? '' : 's'} · ${formatCurrency(subtotal(lines))}` : 'Pick something to send' }}
        </AppButton>
      </footer>
    </div>

    <div v-if="open" class="absolute inset-0 z-50 flex items-end justify-center bg-black/30 sm:items-center" @click.self="open = null">
      <div class="max-h-[85vh] w-full max-w-md overflow-y-auto rounded-t-2xl bg-white p-5 sm:rounded-2xl">
        <h3 class="font-display text-xl font-semibold text-brand-900">{{ open.name }}</h3>
        <div v-for="m in open.modifiers" :key="m.id" class="mt-4">
          <p class="font-semibold">{{ m.name }} <span class="text-xs font-normal text-ink-subtle">{{ m.is_required ? 'Required' : 'Optional' }}</span></p>
          <label v-for="o in m.options" :key="o.id" class="mt-2 flex items-center justify-between rounded-lg border border-brand-100 px-3 py-2">
            <span class="flex items-center gap-2 text-sm">
              <input :type="m.max_selections === 1 ? 'radio' : 'checkbox'" :name="`opt-${m.id}`" :checked="(options[m.id] ?? []).includes(o.id)" @change="toggle(m.id, o.id, m.max_selections)">
              {{ o.name }}
            </span>
            <span v-if="Number(o.price_adjustment) > 0" class="text-sm text-ink-muted">+{{ formatCurrency(Number(o.price_adjustment)) }}</span>
          </label>
        </div>
        <label class="mt-4 block text-sm font-medium">Special requests
          <input v-model="note" type="text" maxlength="200" class="mt-1 w-full rounded-lg border border-brand-200 px-3 py-2 text-base">
        </label>
        <div class="mt-4 flex items-center gap-3">
          <button class="h-9 w-9 rounded-full border border-brand-200 text-lg" aria-label="Fewer" @click="qty = Math.max(1, qty - 1)">−</button>
          <span class="w-6 text-center font-semibold">{{ qty }}</span>
          <button class="h-9 w-9 rounded-full border border-brand-200 text-lg" aria-label="More" @click="qty = Math.min(20, qty + 1)">+</button>
        </div>
        <p v-if="error" class="mt-3 text-sm text-red-600">{{ error }}</p>
        <div class="mt-4 flex gap-2">
          <AppButton class="flex-1 py-2.5" @click="addConfigured">Add</AppButton>
          <button class="rounded-lg border px-4 py-2 text-sm" @click="open = null">Cancel</button>
        </div>
      </div>
    </div>
  </div>
</template>
