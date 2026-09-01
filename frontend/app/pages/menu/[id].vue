<script setup lang="ts">
import type { MenuItemDetail } from '~/types/menu'
import { fetchMenuItem } from '~/services/menu'
import { formatCurrency } from '~/utils/format'

const route = useRoute()

const itemId = computed(() => Number(route.params.id))
const item = ref<MenuItemDetail | null>(null)
const loading = ref(true)
const error = ref('')

onMounted(async () => {
  try {
    item.value = await fetchMenuItem(itemId.value)
  }
  catch (err) {
    error.value = err instanceof Error ? err.message : 'Item not found'
  }
  finally {
    loading.value = false
  }
})
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
        <span v-if="!item.is_available" class="rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-600">Unavailable</span>
      </div>
      <h1 class="font-display mt-3 text-3xl font-semibold text-brand-900">{{ item.name }}</h1>
      <p v-if="item.description" class="mt-2 text-ink-muted">{{ item.description }}</p>
      <p class="mt-4 text-2xl font-semibold text-brand-800">{{ formatCurrency(Number(item.price)) }}</p>

      <div v-for="modifier in item.modifiers" :key="modifier.id" class="mt-6 border-t border-brand-100 pt-6">
        <div class="mb-3 flex items-center justify-between">
          <h2 class="font-semibold text-ink">{{ modifier.name }}</h2>
          <span class="text-xs text-ink-subtle">{{ modifier.is_required ? 'Required' : 'Optional' }}</span>
        </div>
        <ul class="space-y-2">
          <li
            v-for="option in modifier.options"
            :key="option.id"
            class="flex items-center justify-between rounded-lg border border-brand-100 px-3 py-2 text-sm"
          >
            <span>{{ option.name }}</span>
            <span v-if="Number(option.price_adjustment) > 0" class="text-ink-muted">
              +{{ formatCurrency(Number(option.price_adjustment)) }}
            </span>
          </li>
        </ul>
      </div>
    </div>
  </div>
</template>
