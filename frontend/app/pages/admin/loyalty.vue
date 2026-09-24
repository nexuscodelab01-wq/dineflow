<script setup lang="ts">
import type { AdminLoyaltyAccount } from '~/types/loyalty'
import { adjustLoyaltyPoints, fetchAdminLoyaltyAccounts } from '~/services/loyalty'

definePageMeta({ layout: 'admin', middleware: ['staff'] })

const admin = useAdminStore()
const ui = useUiStore()

const accounts = ref<AdminLoyaltyAccount[]>([])
const loading = ref(true)
const query = ref('')
const adjustingId = ref<number | null>(null)
const adjustPoints = ref<number | null>(null)
const adjustNote = ref('')
const busyId = ref<number | null>(null)

async function load() {
  if (!admin.restaurantId) return
  accounts.value = await fetchAdminLoyaltyAccounts(admin.restaurantId)
}

onMounted(async () => {
  await admin.initialize()
  await load()
  loading.value = false
})

const filtered = computed(() => {
  const q = query.value.trim().toLowerCase()
  if (!q) return accounts.value
  return accounts.value.filter(a => a.name.toLowerCase().includes(q) || a.email.toLowerCase().includes(q))
})

function startAdjust(account: AdminLoyaltyAccount) {
  adjustingId.value = account.user_id
  adjustPoints.value = null
  adjustNote.value = ''
}

async function submitAdjust(account: AdminLoyaltyAccount) {
  if (!admin.restaurantId || !adjustPoints.value || busyId.value) return
  busyId.value = account.user_id
  try {
    const updated = await adjustLoyaltyPoints(admin.restaurantId, account.user_id, adjustPoints.value, adjustNote.value.trim() || undefined)
    const i = accounts.value.findIndex(a => a.user_id === account.user_id)
    if (i !== -1) accounts.value[i] = updated
    adjustingId.value = null
  }
  catch (err) {
    ui.error(err instanceof Error ? err.message : 'Could not adjust their points')
  }
  finally {
    busyId.value = null
  }
}
</script>

<template>
  <div>
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="font-display text-2xl font-semibold text-brand-900">Loyalty</h1>
        <p class="text-sm text-ink-muted">Points balances, most points first</p>
      </div>
      <input
        v-model="query" type="search" placeholder="Search name or email"
        class="w-56 rounded-lg border border-brand-200 px-3 py-1.5 text-sm"
      >
    </div>

    <div v-if="loading" class="mt-6 h-40 animate-pulse rounded-2xl bg-brand-100/60" />

    <p v-else-if="!filtered.length" class="mt-8 text-sm text-ink-subtle">
      {{ accounts.length ? 'No one matches that search.' : 'No one has earned points yet.' }}
    </p>

    <ul v-else class="mt-6 space-y-3">
      <li v-for="account in filtered" :key="account.user_id" class="rounded-2xl border border-brand-100 bg-surface-elevated p-4">
        <div class="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p class="font-semibold text-ink">{{ account.name }}</p>
            <p class="text-xs text-ink-subtle">{{ account.email }}</p>
          </div>
          <div class="flex items-center gap-3">
            <span class="rounded-full bg-brand-100 px-3 py-1 text-sm font-semibold text-brand-800 tabular-nums">{{ account.balance }} pts</span>
            <button
              type="button" class="rounded-lg border border-brand-200 px-3 py-1.5 text-sm font-medium hover:bg-brand-50"
              @click="startAdjust(account)"
            >
              Adjust
            </button>
          </div>
        </div>

        <div v-if="adjustingId === account.user_id" class="mt-3 flex flex-wrap items-end gap-2 border-t border-brand-100 pt-3">
          <label class="text-sm font-medium">Points <span class="font-normal text-ink-subtle">(negative to deduct)</span>
            <input v-model.number="adjustPoints" type="number" class="mt-1 block w-28 rounded-lg border px-2 py-1.5 text-sm">
          </label>
          <label class="text-sm font-medium">Note <span class="font-normal text-ink-subtle">(optional)</span>
            <input v-model="adjustNote" class="mt-1 block w-56 rounded-lg border px-2 py-1.5 text-sm" placeholder="Sorry about the wait">
          </label>
          <button
            type="button" class="rounded-lg bg-brand-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-800"
            :disabled="!adjustPoints || busyId === account.user_id" @click="submitAdjust(account)"
          >
            Save
          </button>
          <button type="button" class="text-sm text-ink-subtle hover:underline" @click="adjustingId = null">Cancel</button>
        </div>
      </li>
    </ul>
  </div>
</template>
