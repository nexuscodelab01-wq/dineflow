<script setup lang="ts">
import type { Category, MenuItemDetail } from '~/types/menu'
import { createMenuItem, deleteMenuItem, fetchAdminCategories, fetchAdminMenu, updateMenuItem } from '~/services/admin'
import { formatCurrency } from '~/utils/format'

definePageMeta({ layout: 'admin', middleware: ['staff'] })

const auth = useAuthStore()
const admin = useAdminStore()
const items = ref<MenuItemDetail[]>([])
const categories = ref<Category[]>([])
const loading = ref(true)
const search = ref('')
const showForm = ref(false)
const editing = ref<MenuItemDetail | null>(null)
const error = ref('')
const notice = ref('')

const form = reactive({
  name: '',
  description: '',
  price: '',
  category_id: 0,
  is_available: true,
  is_vegetarian: false,
  is_spicy: false,
  is_popular: false,
})

async function load() {
  await admin.initialize()
  if (!admin.restaurantId) return
  loading.value = true
  try {
    ;[items.value, categories.value] = await Promise.all([
      fetchAdminMenu(admin.restaurantId),
      fetchAdminCategories(admin.restaurantId),
    ])
  }
  finally {
    loading.value = false
  }
}

onMounted(load)

const filtered = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return items.value
  return items.value.filter(i => i.name.toLowerCase().includes(q) || i.description?.toLowerCase().includes(q))
})

function openCreate() {
  editing.value = null
  Object.assign(form, { name: '', description: '', price: '', category_id: categories.value[0]?.id || 0, is_available: true, is_vegetarian: false, is_spicy: false, is_popular: false })
  showForm.value = true
}

function openEdit(item: MenuItemDetail) {
  editing.value = item
  Object.assign(form, {
    name: item.name,
    description: item.description || '',
    price: item.price,
    category_id: item.category_id,
    is_available: item.is_available,
    is_vegetarian: item.is_vegetarian,
    is_spicy: item.is_spicy,
    is_popular: item.is_popular,
  })
  showForm.value = true
}

async function saveItem() {
  if (!admin.restaurantId) return
  error.value = ''
  notice.value = ''
  try {
    const payload = { ...form, price: Number(form.price) }
    if (editing.value) {
      await updateMenuItem(admin.restaurantId, editing.value.id, payload)
      notice.value = 'Menu item updated'
    }
    else if (auth.isAdmin) {
      await createMenuItem(admin.restaurantId, payload)
      notice.value = 'Menu item created'
    }
    showForm.value = false
    await load()
  }
  catch (err) {
    error.value = err instanceof Error ? err.message : 'Save failed'
  }
}

async function removeItem(item: MenuItemDetail) {
  if (!admin.restaurantId || !auth.isAdmin) return
  if (!window.confirm(`Remove "${item.name}" from the menu? This cannot be undone.`)) return
  try {
    await deleteMenuItem(admin.restaurantId, item.id)
    notice.value = 'Menu item deleted'
    await load()
  }
  catch (err) {
    error.value = err instanceof Error ? err.message : 'Delete failed'
  }
}
</script>

<template>
  <div>
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="font-display text-2xl font-semibold text-brand-900">Menu</h1>
        <p class="text-sm text-ink-muted">Manage menu items and availability</p>
      </div>
      <AppButton v-if="auth.isAdmin" @click="openCreate">Add item</AppButton>
    </div>

    <input v-model="search" type="search" placeholder="Search menu…" class="mt-4 w-full max-w-md rounded-lg border border-brand-200 px-3 py-2 text-sm">
    <p v-if="notice" class="mt-3 text-sm text-brand-700">{{ notice }}</p>
    <p v-if="error && !showForm" class="mt-3 text-sm text-red-600">{{ error }}</p>

    <div v-if="loading" class="mt-6 h-40 animate-pulse rounded-2xl bg-brand-100/60" />

    <div
      v-else-if="!filtered.length"
      class="mt-6 rounded-xl border border-brand-100 bg-surface-elevated p-8 text-center"
    >
      <h2 class="font-semibold text-ink">No menu items found</h2>
      <p class="mt-2 text-sm text-ink-muted">Try a different search or add a new item.</p>
    </div>

    <div v-else class="mt-6 overflow-x-auto rounded-2xl border border-brand-100 bg-surface-elevated">
      <table class="min-w-full text-left text-sm">
        <thead class="border-b border-brand-100 bg-brand-50/50 text-xs uppercase tracking-wide text-ink-subtle">
          <tr>
            <th class="px-4 py-3">Item</th>
            <th class="px-4 py-3">Category</th>
            <th class="px-4 py-3">Price</th>
            <th class="px-4 py-3">Status</th>
            <th class="px-4 py-3">Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in filtered" :key="item.id" class="border-b border-brand-50">
            <td class="px-4 py-3 font-medium">{{ item.name }}</td>
            <td class="px-4 py-3 text-ink-muted">{{ item.category_name }}</td>
            <td class="px-4 py-3">{{ formatCurrency(Number(item.price)) }}</td>
            <td class="px-4 py-3">
              <span class="rounded-full px-2 py-0.5 text-xs" :class="item.is_available ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-600'">
                {{ item.is_available ? 'Available' : 'Unavailable' }}
              </span>
            </td>
            <td class="px-4 py-3">
              <button class="mr-2 text-brand-700 hover:underline" @click="openEdit(item)">Edit</button>
              <button v-if="auth.isAdmin" class="text-red-600 hover:underline" @click="removeItem(item)">Delete</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="showForm" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div class="w-full max-w-lg rounded-2xl bg-white p-6 shadow-xl">
        <h2 class="text-lg font-semibold">{{ editing ? 'Edit item' : 'New item' }}</h2>
        <form class="mt-4 space-y-3" @submit.prevent="saveItem">
          <input v-model="form.name" required placeholder="Name" class="w-full rounded-lg border px-3 py-2 text-sm">
          <textarea v-model="form.description" placeholder="Description" class="w-full rounded-lg border px-3 py-2 text-sm" rows="2" />
          <div class="grid grid-cols-2 gap-3">
            <input v-model="form.price" required type="number" step="0.01" min="0" placeholder="Price" class="rounded-lg border px-3 py-2 text-sm">
            <select v-model="form.category_id" class="rounded-lg border px-3 py-2 text-sm">
              <option v-for="cat in categories" :key="cat.id" :value="cat.id">{{ cat.name }}</option>
            </select>
          </div>
          <div class="flex flex-wrap gap-4 text-sm">
            <label class="flex items-center gap-2"><input v-model="form.is_available" type="checkbox"> Available</label>
            <label class="flex items-center gap-2"><input v-model="form.is_popular" type="checkbox"> Popular</label>
            <label class="flex items-center gap-2"><input v-model="form.is_vegetarian" type="checkbox"> Vegetarian</label>
            <label class="flex items-center gap-2"><input v-model="form.is_spicy" type="checkbox"> Spicy</label>
          </div>
          <p v-if="error" class="text-sm text-red-600">{{ error }}</p>
          <div class="flex gap-2 pt-2">
            <AppButton type="submit">Save</AppButton>
            <button type="button" class="rounded-lg border px-4 py-2 text-sm" @click="showForm = false">Cancel</button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>
