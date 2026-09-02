<script setup lang="ts">
import type { MenuItemDetail } from '~/types/menu'
import { fetchMenuItem } from '~/services/menu'
import { formatCurrency } from '~/utils/format'

const route = useRoute()
const router = useRouter()
const cart = useCartStore()

const itemId = computed(() => Number(route.params.id))
const item = ref<MenuItemDetail | null>(null)
const loading = ref(true)
const error = ref('')
const quantity = ref(1)
const specialInstructions = ref('')
const selectedOptions = ref<Record<number, number[]>>({})
const added = ref(false)

onMounted(async () => {
  try {
    item.value = await fetchMenuItem(itemId.value)
    for (const modifier of item.value.modifiers) {
      const defaults = modifier.options.filter(o => o.is_default).map(o => o.id)
      selectedOptions.value[modifier.id] = modifier.max_selections === 1
        ? [defaults[0] || modifier.options[0]?.id].filter(Boolean) as number[]
        : defaults
    }
  }
  catch (err) {
    error.value = err instanceof Error ? err.message : 'Item not found'
  }
  finally {
    loading.value = false
  }
})

const unitPrice = computed(() => {
  if (!item.value) return 0
  let total = Number(item.value.price)
  for (const modifier of item.value.modifiers) {
    const ids = selectedOptions.value[modifier.id] || []
    for (const option of modifier.options) {
      if (ids.includes(option.id)) total += Number(option.price_adjustment)
    }
  }
  return total
})

function toggleOption(modifierId: number, optionId: number, maxSelections: number) {
  const current = selectedOptions.value[modifierId] || []
  if (maxSelections === 1) {
    selectedOptions.value[modifierId] = [optionId]
    return
  }
  if (current.includes(optionId)) {
    selectedOptions.value[modifierId] = current.filter(id => id !== optionId)
  }
  else if (current.length < maxSelections) {
    selectedOptions.value[modifierId] = [...current, optionId]
  }
}

function validationError(): string | null {
  if (!item.value) return 'Item not loaded'
  if (!item.value.is_available) return 'This item is unavailable'
  for (const modifier of item.value.modifiers) {
    const count = (selectedOptions.value[modifier.id] || []).length
    if (modifier.is_required && count < Math.max(modifier.min_selections, 1)) {
      return `Please select ${modifier.name}`
    }
  }
  return null
}

function addToCart() {
  const err = validationError()
  if (err || !item.value) {
    error.value = err || 'Unable to add item'
    return
  }
  const optionIds = Object.values(selectedOptions.value).flat()
  cart.addItem(item.value, optionIds, quantity.value, specialInstructions.value || undefined)
  added.value = true
  setTimeout(() => router.push('/cart'), 600)
}
</script>

<template>
  <div class="mx-auto max-w-3xl px-4 py-8 sm:px-6">
    <NuxtLink to="/menu" class="text-sm font-medium text-brand-700 hover:text-brand-800">← Back to menu</NuxtLink>

    <div v-if="loading" class="mt-8 h-96 animate-pulse rounded-2xl bg-brand-100/60" />

    <div v-else-if="error && !item" class="mt-8 rounded-xl bg-red-50 p-4 text-red-700">
      {{ error }}
    </div>

    <div v-else-if="item" class="mt-6 rounded-2xl border border-brand-100 bg-surface-elevated p-6 shadow-sm">
      <div class="flex flex-wrap gap-2">
        <span v-if="item.is_popular" class="rounded-full bg-brand-100 px-2 py-0.5 text-xs font-medium text-brand-800">Popular</span>
        <span v-if="item.is_vegetarian" class="rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-800">Vegetarian</span>
        <span v-if="item.is_spicy" class="rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-800">Spicy</span>
      </div>
      <h1 class="font-display mt-3 text-3xl font-semibold text-brand-900">{{ item.name }}</h1>
      <p v-if="item.description" class="mt-2 text-ink-muted">{{ item.description }}</p>
      <p class="mt-4 text-2xl font-semibold text-brand-800">{{ formatCurrency(unitPrice) }}</p>

      <div v-for="modifier in item.modifiers" :key="modifier.id" class="mt-6 border-t border-brand-100 pt-6">
        <div class="mb-3 flex items-center justify-between">
          <h2 class="font-semibold text-ink">{{ modifier.name }}</h2>
          <span class="text-xs text-ink-subtle">{{ modifier.is_required ? 'Required' : 'Optional' }}</span>
        </div>
        <div class="space-y-2">
          <label
            v-for="option in modifier.options"
            :key="option.id"
            class="flex cursor-pointer items-center justify-between rounded-lg border border-brand-100 px-3 py-2 hover:bg-brand-50"
          >
            <span class="flex items-center gap-2 text-sm">
              <input
                :type="modifier.max_selections === 1 ? 'radio' : 'checkbox'"
                :name="`modifier-${modifier.id}`"
                :checked="(selectedOptions[modifier.id] || []).includes(option.id)"
                @change="toggleOption(modifier.id, option.id, modifier.max_selections)"
              >
              {{ option.name }}
            </span>
            <span v-if="Number(option.price_adjustment) > 0" class="text-sm text-ink-muted">
              +{{ formatCurrency(Number(option.price_adjustment)) }}
            </span>
          </label>
        </div>
      </div>

      <div class="mt-6 grid gap-4 sm:grid-cols-2">
        <div>
          <label class="mb-1 block text-sm font-medium">Quantity</label>
          <input v-model.number="quantity" type="number" min="1" max="20" class="w-full rounded-lg border border-brand-200 px-3 py-2 text-sm">
        </div>
        <div>
          <label class="mb-1 block text-sm font-medium">Special instructions</label>
          <input v-model="specialInstructions" type="text" class="w-full rounded-lg border border-brand-200 px-3 py-2 text-sm" placeholder="No onions, extra sauce…">
        </div>
      </div>

      <p v-if="error" class="mt-4 text-sm text-red-600">{{ error }}</p>
      <p v-if="added" class="mt-4 text-sm text-brand-700">Added to cart!</p>

      <AppButton class="mt-6 w-full sm:w-auto" :disabled="!item.is_available" @click="addToCart">
        Add to cart — {{ formatCurrency(unitPrice * quantity) }}
      </AppButton>
    </div>
  </div>
</template>
