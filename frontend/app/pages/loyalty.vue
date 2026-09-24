<script setup lang="ts">
import type { LoyaltyAccount } from '~/types/loyalty'
import { fetchMyLoyaltyAccount } from '~/services/loyalty'

definePageMeta({ middleware: ['auth'] })

const loyaltyEnabled = useFeature('loyalty')
const account = ref<LoyaltyAccount | null>(null)
const loading = ref(true)

onMounted(async () => {
  if (!loyaltyEnabled.value) {
    loading.value = false
    return
  }
  try {
    account.value = await fetchMyLoyaltyAccount()
  }
  finally {
    loading.value = false
  }
})

const reasonLabel: Record<string, string> = { EARNED: 'Earned', REDEEMED: 'Redeemed', ADJUSTED: 'Adjustment' }
</script>

<template>
  <div class="mx-auto max-w-2xl px-4 py-12 sm:px-6">
    <p class="text-sm font-semibold uppercase tracking-[0.2em] text-brand-600">Rewards</p>
    <h1 class="font-display mt-2 text-3xl font-semibold text-brand-900">Your points</h1>

    <div v-if="loading" class="mt-8 h-32 animate-pulse rounded-2xl bg-brand-100/60" />

    <p v-else-if="!loyaltyEnabled" class="mt-8 text-sm text-ink-subtle">Loyalty points aren't available here yet.</p>

    <template v-else-if="account">
      <div class="mt-6 rounded-2xl border border-brand-200 bg-surface-elevated p-6 text-center">
        <p class="text-4xl font-semibold tabular-nums text-brand-800">{{ account.balance }}</p>
        <p class="mt-1 text-sm text-ink-muted">
          points · earn {{ account.points_per_currency }} per $1 spent on a completed order
        </p>
      </div>

      <section v-if="account.transactions.length" class="mt-8">
        <h2 class="text-sm font-semibold uppercase tracking-wide text-ink-subtle">History</h2>
        <ul class="mt-3 space-y-2">
          <li
            v-for="t in account.transactions" :key="t.id"
            class="flex items-center justify-between gap-3 rounded-xl border border-brand-100 bg-surface-elevated px-4 py-3 text-sm"
          >
            <div>
              <p class="font-medium text-ink">{{ reasonLabel[t.reason] ?? t.reason }}</p>
              <p class="text-xs text-ink-subtle">
                {{ new Date(t.created_at).toLocaleDateString() }}
                <span v-if="t.note"> · {{ t.note }}</span>
              </p>
            </div>
            <span class="font-semibold tabular-nums" :class="t.points >= 0 ? 'text-emerald-700' : 'text-red-600'">
              {{ t.points >= 0 ? '+' : '' }}{{ t.points }}
            </span>
          </li>
        </ul>
      </section>

      <p v-else class="mt-8 text-sm text-ink-subtle">
        Complete an order here to start earning points.
      </p>
    </template>
  </div>
</template>
