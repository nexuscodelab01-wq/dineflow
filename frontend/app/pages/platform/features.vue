<script setup lang="ts">
import type { Restaurant } from '~/types/menu'
import type { FeatureCatalogEntry, RestaurantFeature } from '~/types/platform'
import {
  createFeature, deleteFeature, fetchAllRestaurants, fetchFeatureCatalog,
  fetchRestaurantFeatures, resetRestaurantFeature, setRestaurantFeature,
} from '~/services/platform'

definePageMeta({ layout: 'platform', middleware: ['platform'] })

const ui = useUiStore()
const catalog = ref<FeatureCatalogEntry[]>([])
const restaurants = ref<Restaurant[]>([])
const loading = ref(true)

async function load() {
  loading.value = true
  try {
    ;[catalog.value, restaurants.value] = await Promise.all([fetchFeatureCatalog(), fetchAllRestaurants()])
  }
  catch (err) {
    ui.error(err instanceof Error ? err.message : 'Could not load feature flags')
  }
  finally {
    loading.value = false
  }
}

onMounted(load)

// ---- creating a flag ---------------------------------------------------------------------------------

const showForm = ref(false)
const form = reactive({ key: '', description: '', default: false })
const creating = ref(false)
const createError = ref('')

function resetForm() {
  Object.assign(form, { key: '', description: '', default: false })
  createError.value = ''
}

async function submitCreate() {
  if (creating.value) return
  creating.value = true
  createError.value = ''
  try {
    await createFeature({ key: form.key.trim().toLowerCase(), description: form.description.trim(), default: form.default })
    ui.success(`'${form.key}' created — nothing checks it yet until it's wired into code`)
    resetForm()
    showForm.value = false
    await load()
  }
  catch (err) {
    createError.value = err instanceof Error ? err.message : 'Could not create the flag'
  }
  finally {
    creating.value = false
  }
}

// ---- deleting a flag ----------------------------------------------------------------------------------

const deleting = ref<string | null>(null)

async function removeFlag(flag: FeatureCatalogEntry) {
  const ok = await ui.confirm({
    title: `Delete '${flag.key}'?`,
    message: 'This also clears every restaurant\'s override of it. If anything in the app still checks this flag, that check will simply always read as off from now on.',
    confirmLabel: 'Delete flag',
    destructive: true,
  })
  if (!ok) return
  deleting.value = flag.key
  try {
    await deleteFeature(flag.key)
    ui.success(`'${flag.key}' deleted`)
    if (selected.value) await loadRestaurantFeatures()
    await load()
  }
  catch (err) {
    ui.error(err instanceof Error ? err.message : 'Could not delete the flag')
  }
  finally {
    deleting.value = null
  }
}

// ---- per-restaurant overrides -------------------------------------------------------------------------

const selected = ref<number | ''>('')
const restaurantFeatures = ref<RestaurantFeature[]>([])
const loadingRestaurant = ref(false)
const saving = ref<string | null>(null)

async function loadRestaurantFeatures() {
  if (!selected.value) {
    restaurantFeatures.value = []
    return
  }
  loadingRestaurant.value = true
  try {
    restaurantFeatures.value = await fetchRestaurantFeatures(selected.value)
  }
  catch (err) {
    ui.error(err instanceof Error ? err.message : 'Could not load this restaurant\'s flags')
  }
  finally {
    loadingRestaurant.value = false
  }
}

watch(selected, loadRestaurantFeatures)

async function choose(flag: RestaurantFeature, value: 'on' | 'off' | 'default') {
  if (!selected.value || saving.value) return
  saving.value = flag.key
  try {
    restaurantFeatures.value = value === 'default'
      ? await resetRestaurantFeature(selected.value, flag.key)
      : await setRestaurantFeature(selected.value, flag.key, value === 'on')
  }
  catch (err) {
    ui.error(err instanceof Error ? err.message : 'Could not change this flag')
  }
  finally {
    saving.value = null
  }
}

function stateOf(flag: RestaurantFeature): 'on' | 'off' | 'default' {
  return flag.override === null ? 'default' : flag.override ? 'on' : 'off'
}
</script>

<template>
  <div>
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="font-display text-3xl font-semibold text-brand-900">Feature flags</h1>
        <p class="text-sm text-ink-muted">The catalog, and each restaurant's own on/off/default choice.</p>
      </div>
      <AppButton @click="showForm = !showForm">{{ showForm ? 'Close' : 'New flag' }}</AppButton>
    </div>

    <section v-if="showForm" class="mt-6 rounded-2xl border border-brand-100 bg-surface-elevated p-6">
      <form class="space-y-4" @submit.prevent="submitCreate">
        <h2 class="font-semibold">New flag</h2>
        <p class="text-xs text-amber-800 bg-amber-100 rounded-lg px-3 py-2">
          Creating a flag here alone does nothing — nothing in the app checks it until a developer adds that check.
          Toggling it for a restaurant afterward won't gate anything by itself.
        </p>
        <label class="block text-sm font-medium">Key
          <input v-model="form.key" required pattern="[a-z][a-z0-9_]*" maxlength="64" class="mt-1 w-full rounded-lg border px-3 py-2 text-sm font-mono" placeholder="table_qr_art">
          <span class="mt-1 block text-xs text-ink-subtle">Lowercase letters, numbers and underscores, starting with a letter.</span>
        </label>
        <label class="block text-sm font-medium">Description
          <input v-model="form.description" required maxlength="500" class="mt-1 w-full rounded-lg border px-3 py-2 text-sm" placeholder="What this flag turns on, in one line">
        </label>
        <label class="flex items-center gap-2 text-sm">
          <input v-model="form.default" type="checkbox"> On by default for every restaurant
        </label>
        <p v-if="createError" class="text-sm text-red-600" role="alert">{{ createError }}</p>
        <AppButton type="submit" :disabled="creating">{{ creating ? 'Creating…' : 'Create flag' }}</AppButton>
      </form>
    </section>

    <div v-if="loading" class="mt-6 h-40 animate-pulse rounded-2xl bg-brand-100/60" />

    <div v-else class="mt-6 overflow-x-auto rounded-2xl border border-brand-100 bg-surface-elevated">
      <table class="min-w-full text-left text-sm">
        <thead class="border-b border-brand-100 bg-brand-50/50 text-xs uppercase tracking-wide text-ink-subtle">
          <tr>
            <th class="px-4 py-3">Key</th>
            <th class="px-4 py-3">Description</th>
            <th class="px-4 py-3">Default</th>
            <th class="px-4 py-3" />
          </tr>
        </thead>
        <tbody>
          <tr v-for="f in catalog" :key="f.key" class="border-b border-brand-50">
            <td class="px-4 py-3 font-mono text-xs font-medium">{{ f.key }}</td>
            <td class="px-4 py-3 text-ink-muted">{{ f.description }}</td>
            <td class="px-4 py-3">{{ f.default ? 'On' : 'Off' }}</td>
            <td class="px-4 py-3 text-right">
              <button class="text-xs font-medium text-red-700 hover:underline" :disabled="deleting === f.key" @click="removeFlag(f)">
                {{ deleting === f.key ? 'Deleting…' : 'Delete' }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <section class="mt-8 rounded-2xl border border-brand-100 bg-surface-elevated p-6">
      <h2 class="font-semibold">Per-restaurant overrides</h2>
      <label class="mt-3 block text-sm font-medium">Restaurant
        <select v-model="selected" class="mt-1 w-full max-w-sm rounded-lg border px-3 py-2 text-sm">
          <option value="">Choose a restaurant…</option>
          <option v-for="r in restaurants" :key="r.id" :value="r.id">{{ r.name }}</option>
        </select>
      </label>

      <div v-if="loadingRestaurant" class="mt-4 h-24 animate-pulse rounded-xl bg-brand-100/60" />

      <div v-else-if="selected" class="mt-4 overflow-x-auto rounded-xl border border-brand-100">
        <table class="min-w-full text-left text-sm">
          <thead class="border-b border-brand-100 bg-brand-50/50 text-xs uppercase tracking-wide text-ink-subtle">
            <tr>
              <th class="px-4 py-3">Flag</th>
              <th class="px-4 py-3">Default</th>
              <th class="px-4 py-3">Choice</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="f in restaurantFeatures" :key="f.key" class="border-b border-brand-50">
              <td class="px-4 py-3">
                <div class="font-mono text-xs font-medium">{{ f.key }}</div>
                <div class="text-xs text-ink-subtle">{{ f.description }}</div>
              </td>
              <td class="px-4 py-3 text-ink-muted">{{ f.default ? 'On' : 'Off' }}</td>
              <td class="px-4 py-3">
                <div class="inline-flex overflow-hidden rounded-lg border border-brand-200 text-xs font-medium">
                  <button
                    v-for="opt in (['on', 'off', 'default'] as const)" :key="opt"
                    class="px-3 py-1.5"
                    :class="stateOf(f) === opt ? 'bg-brand-700 text-white' : 'bg-white text-ink-muted hover:bg-brand-50'"
                    :disabled="saving === f.key"
                    @click="choose(f, opt)"
                  >
                    {{ opt === 'on' ? 'On' : opt === 'off' ? 'Off' : 'Default' }}
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>
