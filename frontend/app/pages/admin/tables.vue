<script setup lang="ts">
import type { RestaurantTable } from '~/types/menu'
import { fetchAdminTables, updateTableStatus } from '~/services/admin'

definePageMeta({ layout: 'admin', middleware: ['staff'] })

const admin = useAdminStore()
const tables = ref<RestaurantTable[]>([])
const loading = ref(true)

const statuses = ['AVAILABLE', 'OCCUPIED', 'RESERVED', 'CLEANING']

async function load() {
  await admin.initialize()
  if (!admin.restaurantId) return
  tables.value = await fetchAdminTables(admin.restaurantId)
  loading.value = false
}

onMounted(load)

async function setStatus(table: RestaurantTable, status: string) {
  if (!admin.restaurantId) return
  await updateTableStatus(admin.restaurantId, table.id, status)
  await load()
}

function statusColor(status: string) {
  if (status === 'AVAILABLE') return 'bg-green-100 text-green-800 border-green-200'
  if (status === 'OCCUPIED') return 'bg-red-100 text-red-800 border-red-200'
  if (status === 'RESERVED') return 'bg-amber-100 text-amber-800 border-amber-200'
  return 'bg-gray-100 text-gray-700 border-gray-200'
}
</script>

<template>
  <div>
    <h1 class="font-display text-2xl font-semibold text-brand-900">Tables</h1>
    <p class="text-sm text-ink-muted">Visual table dashboard</p>

    <div v-if="loading" class="mt-6 h-40 animate-pulse rounded-2xl bg-brand-100/60" />

    <div v-else class="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      <article
        v-for="table in tables"
        :key="table.id"
        class="rounded-2xl border-2 p-5"
        :class="statusColor(table.status)"
      >
        <p class="text-2xl font-bold">Table {{ table.table_number }}</p>
        <p class="mt-1 text-sm">Seats {{ table.capacity }}</p>
        <p class="mt-2 text-xs font-semibold uppercase tracking-wide">{{ table.status }}</p>
        <div class="mt-4 flex flex-wrap gap-1">
          <button
            v-for="status in statuses"
            :key="status"
            class="rounded px-2 py-1 text-xs font-medium bg-white/70 hover:bg-white"
            @click="setStatus(table, status)"
          >
            {{ status }}
          </button>
        </div>
      </article>
    </div>
  </div>
</template>
