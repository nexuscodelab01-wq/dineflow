<script setup lang="ts">
import { onBeforeRouteLeave } from 'vue-router'
import type { RestaurantTable } from '~/types/menu'
import {
  createTable,
  deleteTable,
  fetchAdminTables,
  saveTableLayout,
  updateTable,
} from '~/services/admin'
import type { PlanTable, TableShape } from '~/utils/floorplan'
import { SHAPES, ZONE_PRESETS, findFreeSpot, withLayout, zonesOf } from '~/utils/floorplan'

definePageMeta({ layout: 'admin', middleware: ['admin'] })

const admin = useAdminStore()
const ui = useUiStore()

const tables = ref<RestaurantTable[]>([])
const loading = ref(true)
const error = ref('')
const selectedId = ref<number | null>(null)
const mode = ref<'idle' | 'edit' | 'create'>('idle')
const saving = ref(false)
const savingLayout = ref(false)
/** Positions moved but not saved yet. */
const draft = reactive<Record<number, { x: number, y: number }>>({})

const form = reactive({ table_number: '', capacity: 2, zone: '', shape: 'SQUARE' as TableShape })
const formError = ref('')

const active = computed(() => tables.value.filter(t => t.is_active !== false))
const archived = computed(() => tables.value.filter(t => t.is_active === false))
const selected = computed(() => tables.value.find(t => t.id === selectedId.value) ?? null)
const dirtyCount = computed(() => Object.keys(draft).length)
const zoneOptions = computed(() => [...new Set([...ZONE_PRESETS, ...zonesOf(tables.value)])])

const zoneSummary = computed(() => {
  const groups = new Map<string, { tables: number, seats: number }>()
  for (const t of active.value) {
    const key = t.zone || 'No zone'
    const g = groups.get(key) ?? { tables: 0, seats: 0 }
    g.tables++
    g.seats += t.capacity
    groups.set(key, g)
  }
  return [...groups.entries()].map(([zone, g]) => ({ zone, ...g }))
})
const totalSeats = computed(() => active.value.reduce((n, t) => n + t.capacity, 0))

const planTables = computed<PlanTable[]>(() =>
  active.value.map(t => ({
    id: t.id,
    table_number: t.table_number,
    capacity: t.capacity,
    zone: t.zone,
    shape: t.shape,
    pos_x: draft[t.id]?.x ?? t.pos_x,
    pos_y: draft[t.id]?.y ?? t.pos_y,
    state: 'NEUTRAL',
  })),
)

async function load() {
  await admin.initialize()
  if (!admin.restaurantId) return
  try {
    tables.value = await fetchAdminTables(admin.restaurantId, true)
    error.value = ''
    await placeUnplacedTables()
  }
  catch (err) {
    error.value = err instanceof Error ? err.message : 'Could not load tables'
  }
  finally {
    loading.value = false
  }
}

/** Tables created before floor plans existed have no position: lay them out once and keep it. */
async function placeUnplacedTables() {
  if (!admin.restaurantId) return
  const list = active.value
  if (!list.some(t => t.pos_x == null || t.pos_y == null)) return
  const placed = withLayout(list)
  try {
    await saveTableLayout(
      admin.restaurantId,
      placed.filter((_, i) => list[i]!.pos_x == null || list[i]!.pos_y == null).map(t => ({ id: t.id, pos_x: t.x, pos_y: t.y })),
    )
    tables.value = await fetchAdminTables(admin.restaurantId, true)
  }
  catch { /* the plan still renders with automatic positions */ }
}

onMounted(load)

// ---------------------------------------------------------------- selection & form

function fillForm(t: RestaurantTable) {
  form.table_number = t.table_number
  form.capacity = t.capacity
  form.zone = t.zone ?? ''
  form.shape = (t.shape ?? 'SQUARE') as TableShape
  formError.value = ''
}

function select(id: number) {
  const t = tables.value.find(x => x.id === id)
  if (!t) return
  selectedId.value = id
  mode.value = 'edit'
  fillForm(t)
}

function nextName() {
  let best: { prefix: string, n: number } | null = null
  for (const t of tables.value) {
    const m = /^(.*?)(\d+)$/.exec(t.table_number)
    if (m && (!best || Number(m[2]) > best.n)) best = { prefix: m[1]!, n: Number(m[2]) }
  }
  const taken = new Set(tables.value.map(t => t.table_number))
  let n = best ? best.n + 1 : tables.value.length + 1
  const prefix = best ? best.prefix : 'T'
  while (taken.has(`${prefix}${n}`)) n++
  return `${prefix}${n}`
}

function startCreate() {
  selectedId.value = null
  mode.value = 'create'
  form.table_number = nextName()
  form.capacity = 2
  form.zone = selected.value?.zone ?? ''
  form.shape = 'SQUARE'
  formError.value = ''
}

function cancelForm() {
  mode.value = 'idle'
  selectedId.value = null
  formError.value = ''
}

function onMove(id: number, x: number, y: number) {
  draft[id] = { x, y }
}

// ---------------------------------------------------------------- saving

function payload() {
  return {
    table_number: form.table_number.trim(),
    capacity: Number(form.capacity),
    zone: form.zone.trim() || null,
    shape: form.shape,
  }
}

async function submitForm() {
  if (!admin.restaurantId) return
  formError.value = ''
  const data = payload()
  if (!data.table_number) {
    formError.value = 'Give the table a name'
    return
  }
  if (!Number.isInteger(data.capacity) || data.capacity < 1 || data.capacity > 20) {
    formError.value = 'Seats must be between 1 and 20'
    return
  }
  saving.value = true
  try {
    if (mode.value === 'create') {
      const positions = withLayout(active.value).map(t => ({
        x: draft[t.id]?.x ?? t.x,
        y: draft[t.id]?.y ?? t.y,
      }))
      const spot = findFreeSpot(positions)
      const created = await createTable(admin.restaurantId, { ...data, pos_x: spot.x, pos_y: spot.y })
      ui.success(`Table ${created.table_number} added`)
      await load()
      select(created.id)
    }
    else if (selected.value) {
      const updated = await updateTable(admin.restaurantId, selected.value.id, data)
      ui.success(`Table ${updated.table_number} saved`)
      await load()
      select(updated.id)
    }
  }
  catch (err) {
    formError.value = err instanceof Error ? err.message : 'Could not save the table'
  }
  finally {
    saving.value = false
  }
}

async function saveLayout() {
  if (!admin.restaurantId || !dirtyCount.value) return
  savingLayout.value = true
  try {
    await saveTableLayout(
      admin.restaurantId,
      Object.entries(draft).map(([id, p]) => ({ id: Number(id), pos_x: p.x, pos_y: p.y })),
    )
    for (const id of Object.keys(draft)) delete draft[Number(id)]
    ui.success('Floor plan saved')
    await load()
  }
  catch (err) {
    ui.error(err instanceof Error ? err.message : 'Could not save the layout')
  }
  finally {
    savingLayout.value = false
  }
}

function discardLayout() {
  for (const id of Object.keys(draft)) delete draft[Number(id)]
}

// ---------------------------------------------------------------- retire / delete

async function setActive(t: RestaurantTable, isActive: boolean) {
  if (!admin.restaurantId) return
  if (!isActive) {
    const ok = await ui.confirm({
      title: `Take table ${t.table_number} out of service?`,
      message: 'It disappears from the seating plan and can no longer be booked. Its booking history is kept, and you can bring it back any time.',
      confirmLabel: 'Take out of service',
      destructive: true,
    })
    if (!ok) return
  }
  try {
    await updateTable(admin.restaurantId, t.id, { is_active: isActive })
    ui.success(isActive ? `Table ${t.table_number} is back in service` : `Table ${t.table_number} taken out of service`)
    if (!isActive && selectedId.value === t.id) cancelForm()
    await load()
  }
  catch (err) {
    ui.error(err instanceof Error ? err.message : 'Could not update the table')
  }
}

async function remove(t: RestaurantTable) {
  if (!admin.restaurantId) return
  const ok = await ui.confirm({
    title: `Delete table ${t.table_number}?`,
    message: 'This permanently removes the table. This cannot be undone.',
    confirmLabel: 'Delete table',
    destructive: true,
  })
  if (!ok) return
  try {
    await deleteTable(admin.restaurantId, t.id)
    ui.success(`Table ${t.table_number} deleted`)
    if (selectedId.value === t.id) cancelForm()
    delete draft[t.id]
    await load()
  }
  catch (err) {
    const message = err instanceof Error ? err.message : 'Could not delete the table'
    // Tables with booking history can't be deleted — offer the supported alternative.
    if (/out of service/.test(message) && t.is_active !== false) {
      await setActive(t, false)
    }
    else {
      ui.error(message)
    }
  }
}

// ---------------------------------------------------------------- unsaved-changes guard

onBeforeRouteLeave(async () => {
  if (!dirtyCount.value) return true
  return await ui.confirm({
    title: 'Leave without saving?',
    message: `You moved ${dirtyCount.value} table${dirtyCount.value === 1 ? '' : 's'} but haven't saved the layout.`,
    confirmLabel: 'Leave and discard',
    cancelLabel: 'Stay',
    destructive: true,
  })
})

function warnBeforeUnload(event: BeforeUnloadEvent) {
  if (dirtyCount.value) event.preventDefault()
}
onMounted(() => window.addEventListener('beforeunload', warnBeforeUnload))
onBeforeUnmount(() => window.removeEventListener('beforeunload', warnBeforeUnload))
</script>

<template>
  <div>
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h1 class="font-display text-2xl font-semibold text-brand-900">Floor plan</h1>
        <p class="text-sm text-ink-muted">
          Add and name your tables, group them into zones, and arrange them like your dining room.
          Customers see this plan when they book.
        </p>
      </div>
      <AppButton @click="startCreate">Add table</AppButton>
    </div>

    <div
      v-if="dirtyCount"
      class="sticky top-0 z-20 mt-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 shadow-sm"
      role="status"
    >
      <span>{{ dirtyCount }} table{{ dirtyCount === 1 ? '' : 's' }} moved — layout not saved yet.</span>
      <span class="flex gap-2">
        <button type="button" class="rounded-lg border border-amber-300 bg-white px-3 py-1.5 font-medium hover:bg-amber-100" @click="discardLayout">Discard</button>
        <button type="button" class="rounded-lg bg-brand-700 px-3 py-1.5 font-semibold text-white hover:bg-brand-800 disabled:opacity-50" :disabled="savingLayout" @click="saveLayout">
          {{ savingLayout ? 'Saving…' : 'Save layout' }}
        </button>
      </span>
    </div>

    <ErrorState v-if="error" class="mt-6" :message="error" @retry="load" />
    <LoadingState v-else-if="loading" class="mt-6" :rows="1" height-class="h-96" />

    <div v-else class="mt-6 grid gap-6 lg:grid-cols-3">
      <div class="lg:col-span-2">
        <FloorPlan
          :tables="planTables"
          :selected-id="selectedId"
          editable
          @select="select"
          @move="onMove"
        />

        <div class="mt-4 flex flex-wrap items-center gap-2 text-sm">
          <span class="rounded-full bg-brand-100 px-3 py-1 font-medium text-brand-900">
            {{ active.length }} tables · {{ totalSeats }} seats
          </span>
          <span
            v-for="z in zoneSummary"
            :key="z.zone"
            class="rounded-full border border-brand-200 px-3 py-1 text-ink-muted"
          >
            {{ z.zone }} · {{ z.tables }} · {{ z.seats }} seats
          </span>
        </div>

        <section v-if="archived.length" class="mt-8">
          <h2 class="font-semibold text-ink">Out of service</h2>
          <p class="text-sm text-ink-muted">Hidden from bookings and the seating plan. History is kept.</p>
          <ul class="mt-3 divide-y divide-brand-100 rounded-2xl border border-brand-100 bg-surface-elevated">
            <li v-for="t in archived" :key="t.id" class="flex flex-wrap items-center justify-between gap-2 px-4 py-3 text-sm">
              <span>
                <span class="font-medium">{{ t.table_number }}</span>
                <span class="text-ink-subtle"> · {{ t.capacity }} seats<template v-if="t.zone"> · {{ t.zone }}</template></span>
              </span>
              <span class="flex gap-3">
                <button type="button" class="text-brand-700 hover:underline" @click="setActive(t, true)">Bring back</button>
                <button type="button" class="text-red-600 hover:underline" @click="remove(t)">Delete</button>
              </span>
            </li>
          </ul>
        </section>
      </div>

      <aside class="lg:col-span-1">
        <div class="rounded-2xl border border-brand-100 bg-surface-elevated p-5 lg:sticky lg:top-4">
          <template v-if="mode === 'idle'">
            <h2 class="font-semibold text-ink">Tables</h2>
            <p class="mt-2 text-sm text-ink-muted">
              Select a table on the plan to rename it, change its seats, zone or shape.
              Drag tables to arrange them, then save the layout.
            </p>
            <p v-if="!active.length" class="mt-4 rounded-lg bg-brand-50 px-3 py-3 text-sm text-brand-900">
              No tables yet. Use <strong>Add table</strong> to create your first one.
            </p>
          </template>

          <form v-else class="space-y-4" @submit.prevent="submitForm">
            <h2 class="font-semibold text-ink">
              {{ mode === 'create' ? 'New table' : `Table ${selected?.table_number}` }}
            </h2>

            <label class="block text-sm">
              <span class="mb-1 block font-medium">Name</span>
              <input v-model="form.table_number" required maxlength="20" placeholder="e.g. T1, Window 3, Bar 2" class="w-full rounded-lg border border-brand-200 px-3 py-2">
            </label>

            <label class="block text-sm">
              <span class="mb-1 block font-medium">Seats</span>
              <input v-model.number="form.capacity" type="number" min="1" max="20" required class="w-full rounded-lg border border-brand-200 px-3 py-2">
            </label>

            <label class="block text-sm">
              <span class="mb-1 block font-medium">Zone</span>
              <input v-model="form.zone" list="zone-options" maxlength="50" placeholder="Window, Center, Bar, Patio…" class="w-full rounded-lg border border-brand-200 px-3 py-2">
              <datalist id="zone-options">
                <option v-for="z in zoneOptions" :key="z" :value="z" />
              </datalist>
              <span class="mt-1 block text-xs text-ink-subtle">Customers can filter the plan by zone. Type your own if none fit.</span>
            </label>

            <fieldset class="text-sm">
              <legend class="mb-1 font-medium">Shape</legend>
              <div class="flex gap-2">
                <label
                  v-for="s in SHAPES"
                  :key="s.value"
                  class="flex flex-1 cursor-pointer flex-col items-center gap-1 rounded-lg border-2 px-2 py-2 text-xs"
                  :class="form.shape === s.value ? 'border-brand-700 bg-brand-50' : 'border-brand-100 hover:border-brand-300'"
                >
                  <input v-model="form.shape" type="radio" name="shape" :value="s.value" class="sr-only">
                  <svg viewBox="0 0 24 16" class="h-6 w-9" aria-hidden="true">
                    <circle v-if="s.value === 'ROUND'" cx="12" cy="8" r="6" fill="#dceee5" stroke="#3a8b68" stroke-width="1.2" />
                    <rect v-else-if="s.value === 'SQUARE'" x="6" y="2" width="12" height="12" rx="1.5" fill="#dceee5" stroke="#3a8b68" stroke-width="1.2" />
                    <rect v-else x="2" y="4" width="20" height="8" rx="1.5" fill="#dceee5" stroke="#3a8b68" stroke-width="1.2" />
                  </svg>
                  {{ s.label }}
                </label>
              </div>
            </fieldset>

            <p v-if="formError" class="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">{{ formError }}</p>

            <div class="flex flex-wrap gap-2">
              <AppButton type="submit" :disabled="saving">
                {{ saving ? 'Saving…' : mode === 'create' ? 'Add table' : 'Save changes' }}
              </AppButton>
              <button type="button" class="rounded-lg border border-brand-200 px-4 py-2 text-sm hover:bg-brand-50" @click="cancelForm">
                {{ mode === 'create' ? 'Cancel' : 'Close' }}
              </button>
            </div>

            <div v-if="mode === 'edit' && selected" class="space-y-2 border-t border-brand-100 pt-4 text-sm">
              <button type="button" class="block text-left text-amber-800 hover:underline" @click="setActive(selected, false)">
                Take out of service
              </button>
              <button type="button" class="block text-left text-red-600 hover:underline" @click="remove(selected)">
                Delete table
              </button>
            </div>
          </form>
        </div>
      </aside>
    </div>
  </div>
</template>
