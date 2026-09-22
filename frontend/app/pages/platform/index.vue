<script setup lang="ts">
import type { Restaurant } from '~/types/menu'
import { COMMON_TIMEZONES } from '~/utils/timezones'
import { createTenant, fetchAllRestaurants, fetchTenantTemplates, verifyRestaurantDomain } from '~/services/platform'
import type { TenantCreateResponse } from '~/types/platform'

definePageMeta({ layout: 'platform', middleware: ['platform'] })

const ui = useUiStore()
const restaurants = ref<Restaurant[]>([])
const templates = ref<string[]>([])
const loading = ref(true)
const showForm = ref(false)

async function load() {
  loading.value = true
  try {
    ;[restaurants.value, templates.value] = await Promise.all([fetchAllRestaurants(), fetchTenantTemplates()])
  }
  catch (err) {
    ui.error(err instanceof Error ? err.message : 'Could not load restaurants')
  }
  finally {
    loading.value = false
  }
}

onMounted(load)

// ---- creating a restaurant --------------------------------------------------------------------------

const form = reactive({
  name: '', slug: '', ownerEmail: '', ownerName: '', color: '#2c6f53', secondaryColor: '', template: 'generic', timezone: 'UTC',
  customDomain: '', branding: true, sendInvite: false,
})
const slugTouched = ref(false)
const logoFile = ref<File | null>(null)
const logoPreview = ref<string | null>(null)
const creating = ref(false)
const createError = ref('')
const created = ref<TenantCreateResponse | null>(null)

function slugify(value: string) {
  // Drop apostrophes rather than treating them as a separator, so "Luigi's" becomes "luigis" not "luigi-s"
  // — matching how the backend derives the restaurant's order-number prefix from the same name.
  return value.toLowerCase().trim().replace(/['’]/g, '').replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 60)
}

watch(() => form.name, (name) => {
  if (!slugTouched.value) form.slug = slugify(name)
})

function onSlugInput() {
  slugTouched.value = true
  form.slug = slugify(form.slug)
}

function onLogoSelected(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0] ?? null
  logoFile.value = file
  logoPreview.value = file ? URL.createObjectURL(file) : null
}

function resetForm() {
  Object.assign(form, { name: '', slug: '', ownerEmail: '', ownerName: '', color: '#2c6f53', secondaryColor: '', template: 'generic', timezone: 'UTC', customDomain: '', branding: true, sendInvite: false })
  slugTouched.value = false
  logoFile.value = null
  logoPreview.value = null
  created.value = null
  createError.value = ''
}

async function submit() {
  if (creating.value) return
  creating.value = true
  createError.value = ''
  try {
    created.value = await createTenant({
      name: form.name.trim(), slug: form.slug, owner_email: form.ownerEmail.trim(), owner_name: form.ownerName.trim() || undefined,
      color: form.color || undefined, secondary_color: form.secondaryColor || undefined, template: form.template, timezone: form.timezone,
      custom_domain: form.customDomain.trim() || undefined, branding: form.branding, send_invite: form.sendInvite,
      logo: logoFile.value,
    })
    ui.success(`${created.value.name} is ready`)
    await load()
  }
  catch (err) {
    createError.value = err instanceof Error ? err.message : 'Could not create the restaurant'
  }
  finally {
    creating.value = false
  }
}

function startAnother() {
  resetForm()
}

// ---- domain verification (mock) ----------------------------------------------------------------------

const verifying = ref<number | null>(null)

async function verify(restaurant: Restaurant) {
  if (verifying.value) return
  verifying.value = restaurant.id
  try {
    const updated = await verifyRestaurantDomain(restaurant.id)
    restaurants.value = restaurants.value.map(r => (r.id === updated.id ? updated : r))
    ui.success('Domain marked as verified')
  }
  catch (err) {
    ui.error(err instanceof Error ? err.message : 'Could not verify the domain')
  }
  finally {
    verifying.value = null
  }
}
</script>

<template>
  <div>
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="font-display text-3xl font-semibold text-brand-900">Restaurants</h1>
        <p class="text-sm text-ink-muted">Every tenant on this platform.</p>
      </div>
      <AppButton @click="showForm = !showForm">{{ showForm ? 'Close' : 'New restaurant' }}</AppButton>
    </div>

    <section v-if="showForm" class="mt-6 rounded-2xl border border-brand-100 bg-surface-elevated p-6">
      <div v-if="created" class="space-y-3">
        <h2 class="font-display text-xl font-semibold text-brand-900">{{ created.name }} is ready</h2>
        <dl class="grid gap-2 text-sm sm:grid-cols-2">
          <div><dt class="text-ink-subtle">Site</dt><dd><a :href="created.site_url" target="_blank" class="text-brand-700 underline">{{ created.site_url }}</a></dd></div>
          <div><dt class="text-ink-subtle">Order numbers</dt><dd>{{ created.order_prefix }}-1001…</dd></div>
          <div class="sm:col-span-2"><dt class="text-ink-subtle">Owner</dt><dd>{{ created.owner_email }}</dd></div>
          <div v-if="created.invite_link" class="sm:col-span-2">
            <dt class="text-ink-subtle">Set-password link (one-time, valid 7 days) — send this to the owner</dt>
            <dd class="mt-1 break-all rounded-lg bg-surface-muted/60 p-2 font-mono text-xs">{{ created.invite_link }}</dd>
          </div>
        </dl>
        <div class="flex gap-2 pt-2">
          <AppButton @click="startAnother">Create another</AppButton>
          <button class="rounded-lg border px-4 py-2 text-sm" @click="showForm = false">Done</button>
        </div>
      </div>

      <form v-else class="space-y-4" @submit.prevent="submit">
        <h2 class="font-semibold">New restaurant</h2>
        <div class="grid gap-3 sm:grid-cols-2">
          <label class="block text-sm font-medium">Restaurant name
            <input v-model="form.name" required class="mt-1 w-full rounded-lg border px-3 py-2 text-sm" placeholder="Luigi's Trattoria">
          </label>
          <label class="block text-sm font-medium">Site address (slug)
            <div class="mt-1 flex items-center gap-1 text-sm">
              <input v-model="form.slug" required pattern="[a-z0-9]+(-[a-z0-9]+)*" class="w-full rounded-lg border px-3 py-2" placeholder="luigis" @input="onSlugInput">
            </div>
            <span class="mt-1 block text-xs text-ink-subtle">Their site: {{ form.slug || '…' }}.&lt;your platform domain&gt;</span>
          </label>
        </div>

        <div class="grid gap-3 sm:grid-cols-2">
          <label class="block text-sm font-medium">Owner email
            <input v-model="form.ownerEmail" type="email" required class="mt-1 w-full rounded-lg border px-3 py-2 text-sm" placeholder="owner@restaurant.com">
          </label>
          <label class="block text-sm font-medium">Owner name
            <input v-model="form.ownerName" class="mt-1 w-full rounded-lg border px-3 py-2 text-sm" placeholder="Luigi Rossi">
          </label>
        </div>

        <div class="rounded-xl border border-brand-100 p-4">
          <h3 class="text-sm font-semibold">Branding</h3>
          <div class="mt-3 grid gap-3 sm:grid-cols-2">
            <label class="block text-sm font-medium">Primary colour <span class="font-normal text-ink-subtle">(buttons, links)</span>
              <div class="mt-1 flex items-center gap-2">
                <input v-model="form.color" type="color" class="h-9 w-14 cursor-pointer rounded border">
                <input v-model="form.color" type="text" class="w-full rounded-lg border px-3 py-2 text-sm" placeholder="#2c6f53">
              </div>
            </label>
            <label class="block text-sm font-medium">Secondary colour <span class="font-normal text-ink-subtle">(badges, highlights — optional)</span>
              <div class="mt-1 flex items-center gap-2">
                <input v-model="form.secondaryColor" type="color" class="h-9 w-14 cursor-pointer rounded border">
                <input v-model="form.secondaryColor" type="text" class="w-full rounded-lg border px-3 py-2 text-sm" placeholder="#f1c40f">
              </div>
            </label>
            <label class="block text-sm font-medium sm:col-span-2">Logo
              <input type="file" accept="image/png,image/jpeg,image/webp,image/gif" class="mt-1 block w-full text-sm" @change="onLogoSelected">
            </label>
          </div>
          <img v-if="logoPreview" :src="logoPreview" alt="Logo preview" class="mt-3 h-16 w-auto rounded border border-brand-100 bg-white object-contain p-1">
          <label class="mt-3 flex items-center gap-2 text-sm">
            <input v-model="form.branding" type="checkbox"> Use this restaurant's own colours and logo on its site
          </label>
        </div>

        <div class="grid gap-3 sm:grid-cols-2">
          <label class="block text-sm font-medium">Menu template
            <select v-model="form.template" class="mt-1 w-full rounded-lg border px-3 py-2 text-sm">
              <option v-for="t in templates" :key="t" :value="t">{{ t }}</option>
            </select>
          </label>
          <label class="block text-sm font-medium">Timezone
            <select v-model="form.timezone" class="mt-1 w-full rounded-lg border px-3 py-2 text-sm">
              <option v-for="tz in COMMON_TIMEZONES" :key="tz.value" :value="tz.value">{{ tz.label }}</option>
            </select>
          </label>
        </div>

        <label class="block text-sm font-medium">Custom domain <span class="font-normal text-ink-subtle">(optional — can be added later)</span>
          <input v-model="form.customDomain" class="mt-1 w-full rounded-lg border px-3 py-2 text-sm" placeholder="order.theirrestaurant.com">
        </label>

        <label class="flex items-center gap-2 text-sm">
          <input v-model="form.sendInvite" type="checkbox"> Email the owner their set-password link (otherwise you'll get a link to send yourself)
        </label>

        <p v-if="createError" class="text-sm text-red-600" role="alert">{{ createError }}</p>
        <AppButton type="submit" :disabled="creating">{{ creating ? 'Creating…' : 'Create restaurant' }}</AppButton>
      </form>
    </section>

    <div v-if="loading" class="mt-6 h-40 animate-pulse rounded-2xl bg-brand-100/60" />

    <div v-else class="mt-6 overflow-x-auto rounded-2xl border border-brand-100 bg-surface-elevated">
      <table class="min-w-full text-left text-sm">
        <thead class="border-b border-brand-100 bg-brand-50/50 text-xs uppercase tracking-wide text-ink-subtle">
          <tr>
            <th class="px-4 py-3">Restaurant</th>
            <th class="px-4 py-3">Site</th>
            <th class="px-4 py-3">Custom domain</th>
            <th class="px-4 py-3">Status</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in restaurants" :key="r.id" class="border-b border-brand-50">
            <td class="px-4 py-3 font-medium">{{ r.name }}</td>
            <td class="px-4 py-3 text-ink-muted">{{ r.slug }}</td>
            <td class="px-4 py-3">{{ r.custom_domain || '—' }}</td>
            <td class="px-4 py-3">
              <span v-if="!r.custom_domain" class="text-ink-subtle">—</span>
              <span v-else-if="r.domain_verified_at" class="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-semibold text-emerald-900">Verified</span>
              <div v-else class="flex items-center gap-2">
                <span class="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-900">Pending verification</span>
                <button class="text-xs font-medium text-brand-700 hover:underline" :disabled="verifying === r.id" @click="verify(r)">
                  {{ verifying === r.id ? 'Verifying…' : 'Mark verified' }}
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
      <p class="border-t border-brand-100 px-4 py-3 text-xs text-ink-subtle">
        Domain verification is a placeholder for real DNS/TLS automation — it doesn't check DNS yet, it just records that you checked it by hand.
      </p>
    </div>
  </div>
</template>
