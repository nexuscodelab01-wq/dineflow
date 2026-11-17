<script setup lang="ts">
import type { Category, MenuItemDetail, MenuLabel } from '~/types/menu'
import {
  createCategory,
  createLabel,
  deleteCategory,
  deleteLabel,
  fetchAdminCategories,
  fetchAdminLabels,
  reorderCategories,
  updateCategory,
  updateLabel,
} from '~/services/admin'

/**
 * Where an owner manages the words a menu is built from: its categories, the allergens a dish can contain and its own
 * dish types (Vegan, Gluten-free, …). Everything here is the restaurant's own — even the standard allergens can be
 * renamed or removed. Staff can look; only admins can change.
 */
const props = defineProps<{ restaurantId: number, items: MenuItemDetail[], canEdit: boolean, initialTab?: Tab }>()
const emit = defineEmits<{ close: [], changed: [] }>()

type Tab = 'categories' | 'allergen' | 'dish_type'
const tab = ref<Tab>(props.initialTab ?? 'categories')
const ui = useUiStore()

const categories = ref<Category[]>([])
const labels = ref<MenuLabel[]>([])
const loading = ref(true)
const busy = ref(false)
const newName = ref('')
const renamingId = ref<number | null>(null)
const renameValue = ref('')

const TABS: { key: Tab, title: string, hint: string, noun: string, empty: string }[] = [
  { key: 'categories', title: 'Categories', noun: 'category', hint: 'The sections of your menu, in the order guests see them.', empty: 'No categories yet.' },
  { key: 'allergen', title: 'Allergens', noun: 'allergen', hint: 'What a dish can contain, so guests with allergies can avoid it.', empty: 'No allergens. Add the ones your dishes contain.' },
  { key: 'dish_type', title: 'Dish types', noun: 'dish type', hint: 'Badges you give dishes, like Vegan, Gluten-free or Chef’s pick. Guests can filter by them.', empty: 'No dish types yet. Add your first one below.' },
]
const current = computed(() => TABS.find(t => t.key === tab.value)!)

type Row = { id: number, name: string, count: number }
const rows = computed<Row[]>(() => {
  if (tab.value === 'categories') {
    return categories.value.map(c => ({ id: c.id, name: c.name, count: props.items.filter(i => i.category_id === c.id).length }))
  }
  return labels.value.filter(l => l.kind === tab.value).map(l => ({ id: l.id, name: l.label, count: l.item_count ?? 0 }))
})

async function load() {
  loading.value = true
  try {
    ;[categories.value, labels.value] = await Promise.all([
      fetchAdminCategories(props.restaurantId),
      fetchAdminLabels(props.restaurantId),
    ])
  }
  catch (err) {
    ui.error(err instanceof Error ? err.message : 'Could not load')
  }
  finally {
    loading.value = false
  }
}
onMounted(load)

function pick(next: Tab) {
  tab.value = next
  newName.value = ''
  renamingId.value = null
}

function slugify(name: string) {
  return name.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'category'
}

/** Run a change, then refresh the lists and tell the page so the menu behind it updates. */
async function run(action: () => Promise<unknown>, done?: string) {
  busy.value = true
  try {
    await action()
    await load()
    emit('changed')
    if (done) ui.success(done)
  }
  catch (err) {
    ui.error(err instanceof Error ? err.message : 'Something went wrong')
  }
  finally {
    busy.value = false
  }
}

async function add() {
  const name = newName.value.trim()
  if (!name || !props.canEdit) return
  await run(async () => {
    if (tab.value === 'categories') {
      await createCategory(props.restaurantId, { name, slug: slugify(name), sort_order: categories.value.length })
    }
    else {
      await createLabel(props.restaurantId, tab.value, name)
    }
    newName.value = ''
  }, `“${name}” added`)
}

function startRename(row: Row) {
  renamingId.value = row.id
  renameValue.value = row.name
}

async function saveRename(row: Row) {
  const name = renameValue.value.trim()
  renamingId.value = null
  if (!name || name === row.name) return
  await run(() => tab.value === 'categories'
    ? updateCategory(props.restaurantId, row.id, { name })
    : updateLabel(props.restaurantId, row.id, name), 'Renamed')
}

async function remove(row: Row) {
  const isCategory = tab.value === 'categories'
  if (isCategory && row.count) {
    ui.error(`“${row.name}” still has ${row.count} dish${row.count === 1 ? '' : 'es'}. Move or delete them first.`)
    return
  }
  const used = !isCategory && row.count
    ? ` It will also be taken off the ${row.count} dish${row.count === 1 ? '' : 'es'} that use${row.count === 1 ? 's' : ''} it.`
    : ''
  const ok = await ui.confirm({
    title: `Delete ${current.value.noun}`,
    message: `Delete “${row.name}”?${used} This cannot be undone.`,
    confirmLabel: 'Delete',
    destructive: true,
  })
  if (!ok) return
  await run(() => isCategory ? deleteCategory(props.restaurantId, row.id) : deleteLabel(props.restaurantId, row.id), 'Deleted')
}

async function move(index: number, by: -1 | 1) {
  const list = [...categories.value]
  const target = index + by
  if (target < 0 || target >= list.length) return
  ;[list[index], list[target]] = [list[target]!, list[index]!]
  await run(() => reorderCategories(props.restaurantId, list.map((c, i) => ({ id: c.id, sort_order: i }))))
}
</script>

<template>
  <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" @keydown.esc="emit('close')">
    <div class="flex max-h-[90vh] w-full max-w-lg flex-col rounded-2xl bg-white shadow-xl" role="dialog" aria-modal="true" aria-label="Categories, allergens and dish types">
      <div class="flex items-center justify-between border-b border-brand-100 px-6 py-4">
        <h2 class="text-lg font-semibold">Categories, allergens &amp; dish types</h2>
        <button type="button" class="rounded-lg px-2 py-1 text-ink-muted hover:bg-brand-50" aria-label="Close" @click="emit('close')">✕</button>
      </div>

      <div class="flex gap-1 border-b border-brand-100 px-4 pt-3" role="tablist">
        <button
          v-for="t in TABS"
          :key="t.key"
          type="button"
          role="tab"
          :aria-selected="tab === t.key"
          class="rounded-t-lg px-3 py-2 text-sm font-medium"
          :class="tab === t.key ? 'bg-brand-50 text-brand-800' : 'text-ink-muted hover:text-ink'"
          @click="pick(t.key)"
        >
          {{ t.title }}
        </button>
      </div>

      <div class="overflow-y-auto px-6 py-4">
        <p class="text-sm text-ink-muted">{{ current.hint }}</p>

        <p v-if="loading" class="mt-4 text-sm text-ink-subtle">Loading…</p>
        <p v-else-if="!rows.length" class="mt-4 text-sm text-ink-subtle">{{ current.empty }}</p>

        <ul v-else class="mt-3 divide-y divide-brand-50 rounded-xl border border-brand-100">
          <li v-for="(row, index) in rows" :key="row.id" class="flex items-center gap-2 px-3 py-2 text-sm">
            <template v-if="renamingId === row.id">
              <input
                v-model="renameValue"
                class="min-w-0 flex-1 rounded-lg border px-2 py-1"
                maxlength="100"
                @keydown.enter.prevent="saveRename(row)"
                @keydown.esc.prevent="renamingId = null"
              >
              <button type="button" class="text-brand-700 hover:underline" @click="saveRename(row)">Save</button>
              <button type="button" class="text-ink-muted hover:underline" @click="renamingId = null">Cancel</button>
            </template>
            <template v-else>
              <span class="min-w-0 flex-1 truncate font-medium">{{ row.name }}</span>
              <span class="shrink-0 text-xs text-ink-subtle">{{ row.count }} dish{{ row.count === 1 ? '' : 'es' }}</span>
              <template v-if="canEdit">
                <template v-if="tab === 'categories'">
                  <button type="button" class="px-1 text-ink-muted hover:text-ink disabled:opacity-30" :disabled="busy || index === 0" aria-label="Move up" @click="move(index, -1)">↑</button>
                  <button type="button" class="px-1 text-ink-muted hover:text-ink disabled:opacity-30" :disabled="busy || index === rows.length - 1" aria-label="Move down" @click="move(index, 1)">↓</button>
                </template>
                <button type="button" class="text-brand-700 hover:underline" :disabled="busy" @click="startRename(row)">Rename</button>
                <button type="button" class="text-red-600 hover:underline" :disabled="busy" @click="remove(row)">Delete</button>
              </template>
            </template>
          </li>
        </ul>

        <form v-if="canEdit" class="mt-4 flex gap-2" @submit.prevent="add">
          <input
            v-model="newName"
            :placeholder="`New ${current.noun} name`"
            maxlength="60"
            class="min-w-0 flex-1 rounded-lg border px-3 py-2 text-sm"
          >
          <AppButton type="submit" :disabled="busy || !newName.trim()">Add</AppButton>
        </form>
        <p v-else class="mt-4 text-xs text-ink-subtle">Only an admin can change these.</p>
      </div>

      <div class="border-t border-brand-100 px-6 py-3 text-right">
        <button type="button" class="rounded-lg border px-4 py-2 text-sm" @click="emit('close')">Done</button>
      </div>
    </div>
  </div>
</template>
