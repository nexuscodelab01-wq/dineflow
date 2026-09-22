<script setup lang="ts">
import type { CustomerSummary } from '~/types/admin'
import { fetchAdminCustomers } from '~/services/admin'
import { formatCurrency } from '~/utils/format'

definePageMeta({ layout: 'admin', middleware: ['staff'] })

const admin = useAdminStore()
const customers = ref<CustomerSummary[]>([])
const loading = ref(true)
const search = ref('')

onMounted(async () => {
  await admin.initialize()
  if (admin.restaurantId) {
    customers.value = await fetchAdminCustomers(admin.restaurantId)
  }
  loading.value = false
})

const filtered = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return customers.value
  return customers.value.filter(c =>
    `${c.first_name} ${c.last_name}`.toLowerCase().includes(q) || c.email.toLowerCase().includes(q),
  )
})
</script>

<template>
  <div>
    <h1 class="font-display text-2xl font-semibold text-brand-900">Customers</h1>
    <p class="text-sm text-ink-muted">Everyone who has an account here — ordered, booked, or just signed up</p>

    <div v-if="loading" class="mt-6 h-40 animate-pulse rounded-2xl bg-brand-100/60" />

    <template v-else>
      <input
        v-model="search"
        type="search"
        placeholder="Search by name or email…"
        class="mt-4 w-full max-w-sm rounded-lg border border-brand-200 bg-white px-3 py-2 text-sm outline-none ring-brand-500 focus:ring-2"
      >

      <div class="mt-4 overflow-x-auto rounded-2xl border border-brand-100 bg-surface-elevated">
        <table class="min-w-full text-left text-sm">
          <thead class="border-b border-brand-100 bg-brand-50/50 text-xs uppercase tracking-wide text-ink-subtle">
            <tr>
              <th class="px-4 py-3">Customer</th>
              <th class="px-4 py-3">Email</th>
              <th class="px-4 py-3">Orders</th>
              <th class="px-4 py-3">Bookings</th>
              <th class="px-4 py-3">Spending</th>
              <th class="px-4 py-3">Last seen</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="customer in filtered" :key="customer.id" class="border-b border-brand-50">
              <td class="px-4 py-3">
                <NuxtLink :to="`/admin/customers/${customer.id}`" class="inline-flex items-center gap-1.5 font-medium text-brand-700 hover:underline">
                  {{ customer.first_name }} {{ customer.last_name }}
                  <span v-if="customer.is_vip" class="rounded-full bg-amber-100 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-amber-800" title="VIP">VIP</span>
                  <span v-if="customer.allergies" class="rounded-full bg-red-100 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-red-800" :title="`Allergies: ${customer.allergies}`">⚠</span>
                </NuxtLink>
              </td>
              <td class="px-4 py-3">{{ customer.email }}</td>
              <td class="px-4 py-3">{{ customer.total_orders }}</td>
              <td class="px-4 py-3">{{ customer.total_bookings }}</td>
              <td class="px-4 py-3">{{ formatCurrency(Number(customer.total_spending)) }}</td>
              <td class="px-4 py-3 text-ink-muted">{{ customer.last_seen_at ? new Date(customer.last_seen_at).toLocaleDateString() : '—' }}</td>
            </tr>
            <tr v-if="!filtered.length">
              <td colspan="6" class="px-4 py-6 text-center text-ink-subtle">No customers match.</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>
