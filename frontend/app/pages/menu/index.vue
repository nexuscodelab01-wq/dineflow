<script setup lang="ts">
import type { Category, MenuItem, MenuFilters } from '~/types/menu'
import { fetchCategories, fetchMenu } from '~/services/menu'
import { useDebounceFn } from '@vueuse/core'

const restaurant = useRestaurantStore()
const router = useRouter()

await restaurant.load()

const categories = ref<Category[]>([])
const items = ref<MenuItem[]>([])
const loading = ref(true)
const error = ref('')
const total = ref(0)
const pages = ref(1)

const filters = reactive<MenuFilters>({
  search: '',
  category_id: undefined,
  is_vegetarian: undefined,
  is_spicy: undefined,
  is_popular: undefined,
  sort: 'popular',
  page: 1,
  page_size: 12,
})

async function loadMenu() {
  if (!restaurant.current) return
  loading.value = true
  error.value = ''
  try {
    if (!categories.value.length) {
      categories.value = await fetchCategories(restaurant.current.id)
    }
    const response = await fetchMenu(restaurant.current.id, {
      ...filters,
      search: filters.search || undefined,
    })
    items.value = response.items
    total.value = response.total
    pages.value = response.pages
  }
  catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to load menu'
  }
  finally {
    loading.value = false
  }
}

const debouncedSearch = useDebounceFn(() => {
  filters.page = 1
  loadMenu()
}, 300)

watch(() => filters.search, () => debouncedSearch())
watch(
  () => [filters.category_id, filters.is_vegetarian, filters.is_spicy, filters.is_popular, filters.sort, filters.page],
  () => loadMenu(),
)

onMounted(loadMenu)

function selectCategory(id?: number) {
  filters.category_id = id
  filters.page = 1
}

function goToItem(id: number) {
  router.push(`/menu/${id}`)
}
</script>

<template>
  <div class="mx-auto max-w-6xl px-4 py-8 sm:px-6">
    <div v-if="restaurant.current" class="mb-8">
      <p class="text-sm font-semibold uppercase tracking-[0.2em] text-brand-600">Menu</p>
      <h1 class="font-display mt-2 text-3xl font-semibold text-brand-900 sm:text-4xl">
        {{ restaurant.current.name }}
      </h1>
      <p v-if="restaurant.current.description" class="mt-2 max-w-2xl text-ink-muted">
        {{ restaurant.current.description }}
      </p>
    </div>

    <div class="mb-6 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
      <input
        v-model="filters.search"
        type="search"
        placeholder="Search menu…"
        class="w-full max-w-md rounded-lg border border-brand-200 bg-white px-3 py-2 text-sm outline-none ring-brand-500 focus:ring-2"
      >
      <select
        v-model="filters.sort"
        class="rounded-lg border border-brand-200 bg-white px-3 py-2 text-sm"
      >
        <option value="popular">Popular</option>
        <option value="name">Name</option>
        <option value="price_asc">Price: low to high</option>
        <option value="price_desc">Price: high to low</option>
      </select>
    </div>

    <div class="mb-6 flex flex-wrap gap-2">
      <button
        class="rounded-full px-3 py-1.5 text-sm font-medium transition"
        :class="!filters.category_id ? 'bg-brand-700 text-white' : 'bg-brand-100 text-brand-800 hover:bg-brand-200'"
        @click="selectCategory(undefined)"
      >
        All
      </button>
      <button
        v-for="cat in categories"
        :key="cat.id"
        class="rounded-full px-3 py-1.5 text-sm font-medium transition"
        :class="filters.category_id === cat.id ? 'bg-brand-700 text-white' : 'bg-brand-100 text-brand-800 hover:bg-brand-200'"
        @click="selectCategory(cat.id)"
      >
        {{ cat.name }}
      </button>
    </div>

    <div class="mb-6 flex flex-wrap gap-4 text-sm">
      <label class="flex items-center gap-2"><input v-model="filters.is_vegetarian" type="checkbox" :true-value="true" :false-value="undefined"> Vegetarian</label>
      <label class="flex items-center gap-2"><input v-model="filters.is_spicy" type="checkbox" :true-value="true" :false-value="undefined"> Spicy</label>
      <label class="flex items-center gap-2"><input v-model="filters.is_popular" type="checkbox" :true-value="true" :false-value="undefined"> Popular</label>
    </div>

    <ErrorState v-if="error" :message="error" @retry="loadMenu" />

    <LoadingState v-else-if="loading" :rows="3" height-class="h-64" />

    <EmptyState
      v-else-if="!items.length"
      title="No items match your filters"
      description="Try clearing filters or searching for something else."
    />

    <div v-else class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      <MenuItemCard
        v-for="item in items"
        :key="item.id"
        v-bind="{
          name: item.name,
          description: item.description,
          price: item.price,
          categoryName: item.category_name,
          isVegetarian: item.is_vegetarian,
          isSpicy: item.is_spicy,
          isPopular: item.is_popular,
          unavailable: !item.is_available,
        }"
        @click="goToItem(item.id)"
      />
    </div>

    <div v-if="pages > 1" class="mt-8 flex justify-center gap-2">
      <button
        class="rounded-lg border border-brand-200 px-3 py-1.5 text-sm disabled:opacity-40"
        :disabled="filters.page === 1"
        @click="filters.page = Math.max(1, (filters.page || 1) - 1)"
      >
        Previous
      </button>
      <span class="px-3 py-1.5 text-sm text-ink-muted">Page {{ filters.page }} of {{ pages }}</span>
      <button
        class="rounded-lg border border-brand-200 px-3 py-1.5 text-sm disabled:opacity-40"
        :disabled="filters.page === pages"
        @click="filters.page = Math.min(pages, (filters.page || 1) + 1)"
      >
        Next
      </button>
    </div>
  </div>
</template>
