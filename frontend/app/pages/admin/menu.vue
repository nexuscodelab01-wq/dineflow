<script setup lang="ts">
import type { Category, MenuItemDetail } from '~/types/menu'
import {
  createCategory,
  createMenuItem,
  deleteMenuItem,
  fetchAdminCategories,
  fetchAdminMenu,
  updateMenuItem,
  uploadMenuImage,
} from '~/services/admin'
import { STATIONS } from '~/utils/kitchen'
import { formatCurrency } from '~/utils/format'
import { resolveMediaUrl } from '~/utils/media'

definePageMeta({ layout: 'admin', middleware: ['staff'] })

const auth = useAuthStore()
const admin = useAdminStore()
const ui = useUiStore()
const items = ref<MenuItemDetail[]>([])
const categories = ref<Category[]>([])
const loading = ref(true)
const search = ref('')
const showForm = ref(false)
const editing = ref<MenuItemDetail | null>(null)
const error = ref('')
const uploading = ref(false)
const savingCategory = ref(false)
const showNewCategory = ref(false)
const newCategoryName = ref('')

const form = reactive({
  name: '',
  description: '',
  price: '',
  category_id: 0,
  image_url: '',
  station: 'KITCHEN',
  is_available: true,
  is_vegetarian: false,
  is_spicy: false,
  is_popular: false,
})

const previewUrl = computed(() => resolveMediaUrl(form.image_url || null))

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

function resetFormDefaults() {
  Object.assign(form, {
    name: '',
    description: '',
    price: '',
    category_id: categories.value[0]?.id || 0,
    image_url: '',
    station: 'KITCHEN',
    is_available: true,
    is_vegetarian: false,
    is_spicy: false,
    is_popular: false,
  })
  showNewCategory.value = false
  newCategoryName.value = ''
  error.value = ''
}

function openCreate() {
  editing.value = null
  resetFormDefaults()
  showForm.value = true
}

function openEdit(item: MenuItemDetail) {
  editing.value = item
  Object.assign(form, {
    name: item.name,
    description: item.description || '',
    price: item.price,
    category_id: item.category_id,
    image_url: item.image_url || '',
    station: item.station || 'KITCHEN',
    is_available: item.is_available,
    is_vegetarian: item.is_vegetarian,
    is_spicy: item.is_spicy,
    is_popular: item.is_popular,
  })
  showNewCategory.value = false
  newCategoryName.value = ''
  error.value = ''
  showForm.value = true
}

function slugify(name: string) {
  return name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
    || 'category'
}

async function addCategory() {
  if (!admin.restaurantId || !auth.isAdmin) return
  const name = newCategoryName.value.trim()
  if (!name) {
    error.value = 'Enter a category name'
    return
  }
  savingCategory.value = true
  error.value = ''
  try {
    const created = await createCategory(admin.restaurantId, {
      name,
      slug: slugify(name),
      sort_order: categories.value.length,
      is_active: true,
    })
    categories.value = [...categories.value, created]
    form.category_id = created.id
    newCategoryName.value = ''
    showNewCategory.value = false
    ui.success(`Category "${created.name}" added`)
  }
  catch (err) {
    error.value = err instanceof Error ? err.message : 'Could not create category'
    ui.error(error.value)
  }
  finally {
    savingCategory.value = false
  }
}

async function onImageSelected(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file || !admin.restaurantId) return
  uploading.value = true
  error.value = ''
  try {
    const result = await uploadMenuImage(admin.restaurantId, file)
    form.image_url = result.url
    ui.success('Image uploaded')
  }
  catch (err) {
    error.value = err instanceof Error ? err.message : 'Upload failed'
    ui.error(error.value)
  }
  finally {
    uploading.value = false
    input.value = ''
  }
}

async function saveItem() {
  if (!admin.restaurantId) return
  error.value = ''
  if (!form.category_id) {
    error.value = 'Select or create a category'
    return
  }
  try {
    const payload = {
      name: form.name,
      description: form.description || null,
      price: Number(form.price),
      category_id: Number(form.category_id),
      image_url: form.image_url || null,
      station: form.station,
      is_available: form.is_available,
      is_vegetarian: form.is_vegetarian,
      is_spicy: form.is_spicy,
      is_popular: form.is_popular,
    }
    const wasEditing = Boolean(editing.value)
    if (editing.value) {
      await updateMenuItem(admin.restaurantId, editing.value.id, payload)
    }
    else if (auth.isAdmin) {
      await createMenuItem(admin.restaurantId, payload)
    }
    showForm.value = false
    await load()
    ui.success(wasEditing ? 'Menu item updated' : 'Menu item created')
  }
  catch (err) {
    error.value = err instanceof Error ? err.message : 'Save failed'
    ui.error(error.value)
  }
}

async function removeItem(item: MenuItemDetail) {
  if (!admin.restaurantId || !auth.isAdmin) return
  const confirmed = await ui.confirm({
    title: 'Delete menu item',
    message: `Remove "${item.name}" from the menu? This cannot be undone.`,
    confirmLabel: 'Delete',
    destructive: true,
  })
  if (!confirmed) return
  try {
    await deleteMenuItem(admin.restaurantId, item.id)
    await load()
    ui.success('Menu item deleted')
  }
  catch (err) {
    ui.error(err instanceof Error ? err.message : 'Delete failed')
  }
}
</script>

<template>
  <div>
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="font-display text-2xl font-semibold text-brand-900">Menu</h1>
        <p class="text-sm text-ink-muted">Manage menu items, categories, and photos</p>
      </div>
      <AppButton v-if="auth.isAdmin" @click="openCreate">Add item</AppButton>
    </div>

    <input v-model="search" type="search" placeholder="Search menu…" class="mt-4 w-full max-w-md rounded-lg border border-brand-200 px-3 py-2 text-sm">

    <LoadingState v-if="loading" class="mt-6" :rows="1" />

    <EmptyState
      v-else-if="!filtered.length"
      class="mt-6"
      title="No menu items found"
      description="Try a different search or add a new item."
    />

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
            <td class="px-4 py-3">
              <div class="flex items-center gap-3">
                <div class="h-10 w-10 shrink-0 overflow-hidden rounded-lg bg-brand-50">
                  <img
                    v-if="resolveMediaUrl(item.image_url)"
                    :src="resolveMediaUrl(item.image_url)!"
                    :alt="item.name"
                    class="h-full w-full object-cover"
                  >
                  <span v-else class="flex h-full items-center justify-center text-xs text-brand-700/40">{{ item.name.charAt(0) }}</span>
                </div>
                <span class="font-medium">{{ item.name }}</span>
              </div>
            </td>
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
      <div class="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-2xl bg-white p-6 shadow-xl">
        <h2 class="text-lg font-semibold">{{ editing ? 'Edit item' : 'New item' }}</h2>
        <form class="mt-4 space-y-3" @submit.prevent="saveItem">
          <input v-model="form.name" required placeholder="Name" class="w-full rounded-lg border px-3 py-2 text-sm">
          <textarea v-model="form.description" placeholder="Description" class="w-full rounded-lg border px-3 py-2 text-sm" rows="2" />
          <div class="grid grid-cols-2 gap-3">
            <input v-model="form.price" required type="number" step="0.01" min="0" placeholder="Price" class="rounded-lg border px-3 py-2 text-sm">
            <select v-model.number="form.category_id" class="rounded-lg border px-3 py-2 text-sm">
              <option :value="0" disabled>Select category</option>
              <option v-for="cat in categories" :key="cat.id" :value="cat.id">{{ cat.name }}</option>
            </select>
          </div>

          <div v-if="auth.isAdmin" class="rounded-lg border border-dashed border-brand-200 bg-brand-50/40 p-3">
            <button
              v-if="!showNewCategory"
              type="button"
              class="text-sm font-medium text-brand-700 hover:underline"
              @click="showNewCategory = true"
            >
              + Add new category
            </button>
            <div v-else class="flex flex-wrap gap-2">
              <input
                v-model="newCategoryName"
                type="text"
                placeholder="Category name"
                class="min-w-0 flex-1 rounded-lg border px-3 py-2 text-sm"
                @keydown.enter.prevent="addCategory"
              >
              <button
                type="button"
                class="rounded-lg bg-brand-800 px-3 py-2 text-sm text-white disabled:opacity-50"
                :disabled="savingCategory"
                @click="addCategory"
              >
                {{ savingCategory ? 'Saving…' : 'Create' }}
              </button>
              <button type="button" class="rounded-lg border px-3 py-2 text-sm" @click="showNewCategory = false; newCategoryName = ''">
                Cancel
              </button>
            </div>
          </div>

          <div class="space-y-2">
            <label class="block text-sm font-medium text-ink">Food photo</label>
            <div v-if="previewUrl" class="overflow-hidden rounded-lg border border-brand-100">
              <img :src="previewUrl" alt="Preview" class="h-36 w-full object-cover">
            </div>
            <input
              v-model="form.image_url"
              type="text"
              placeholder="Image URL or uploaded path"
              class="w-full rounded-lg border px-3 py-2 text-sm"
            >
            <div class="flex items-center gap-2">
              <label class="cursor-pointer rounded-lg border border-brand-200 px-3 py-2 text-sm hover:bg-brand-50">
                {{ uploading ? 'Uploading…' : 'Upload image' }}
                <input
                  type="file"
                  accept="image/jpeg,image/png,image/webp,image/gif"
                  class="hidden"
                  :disabled="uploading"
                  @change="onImageSelected"
                >
              </label>
              <button
                v-if="form.image_url"
                type="button"
                class="text-sm text-red-600 hover:underline"
                @click="form.image_url = ''"
              >
                Clear
              </button>
            </div>
            <p class="text-xs text-ink-subtle">Paste a URL or upload JPEG/PNG/WebP/GIF (max 5MB).</p>
          </div>

          <label class="block text-sm font-medium">Made at
            <select v-model="form.station" class="mt-1 w-full rounded-lg border border-brand-200 px-3 py-2 text-sm">
              <option v-for="s in STATIONS" :key="s.key" :value="s.key">{{ s.label }}</option>
            </select>
            <span class="mt-1 block text-xs font-normal text-ink-subtle">Which kitchen screen shows this dish.</span>
          </label>

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
