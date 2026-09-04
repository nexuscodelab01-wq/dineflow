<script setup lang="ts">
import type { CustomerSummary } from '~/types/admin'
import { fetchAdminCustomers } from '~/services/admin'
import { formatCurrency } from '~/utils/format'

definePageMeta({ layout: 'admin', middleware: ['staff'] })

const admin = useAdminStore()
const customers = ref<CustomerSummary[]>([])
const loading = ref(true)

onMounted(async () => {
  await admin.initialize()
  if (admin.restaurantId) {
    customers.value = await fetchAdminCustomers(admin.restaurantId)
  }
  loading.value = false
})
</script>

<template>
  <div>
    <h1 class="font-display text-2xl font-semibold text-brand-900">Customers</h1>
    <p class="text-sm text-ink-muted">Customers who have ordered from this restaurant</p>

    <div v-if="loading" class="mt-6 h-40 animate-pulse rounded-2xl bg-brand-100/60" />

    <div v-else class="mt-6 overflow-x-auto rounded-2xl border border-brand-100 bg-surface-elevated">
      <table class="min-w-full text-left text-sm">
        <thead class="border-b border-brand-100 bg-brand-50/50 text-xs uppercase tracking-wide text-ink-subtle">
          <tr>
            <th class="px-4 py-3">Customer</th>
            <th class="px-4 py-3">Email</th>
            <th class="px-4 py-3">Orders</th>
            <th class="px-4 py-3">Spending</th>
            <th class="px-4 py-3">Last order</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="customer in customers" :key="customer.id" class="border-b border-brand-50">
            <td class="px-4 py-3">
              <NuxtLink :to="`/admin/customers/${customer.id}`" class="font-medium text-brand-700 hover:underline">
                {{ customer.first_name }} {{ customer.last_name }}
              </NuxtLink>
            </td>
            <td class="px-4 py-3">{{ customer.email }}</td>
            <td class="px-4 py-3">{{ customer.total_orders }}</td>
            <td class="px-4 py-3">{{ formatCurrency(Number(customer.total_spending)) }}</td>
            <td class="px-4 py-3 text-ink-muted">{{ customer.last_order_at ? new Date(customer.last_order_at).toLocaleDateString() : '—' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
