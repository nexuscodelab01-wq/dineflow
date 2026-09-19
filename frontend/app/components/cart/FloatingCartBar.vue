<script setup lang="ts">
import { formatCurrency } from '~/utils/format'

const cart = useCartStore()
const route = useRoute()

const hiddenRoutes = new Set(['/cart', '/checkout'])

const visible = computed(() => {
  if (cart.isEmpty) return false
  const path = route.path.replace(/\/$/, '') || '/'
  return !hiddenRoutes.has(path)
})

const itemLabel = computed(() => {
  const n = cart.itemCount
  return n === 1 ? '1 item' : `${n} items`
})
</script>

<template>
  <Teleport to="body">
    <div
      v-if="visible"
      class="pointer-events-none fixed inset-x-0 bottom-0 z-40 flex justify-center px-4 pb-[max(1rem,env(safe-area-inset-bottom))]"
    >
      <div
        class="pointer-events-auto flex w-full max-w-lg items-center gap-3 rounded-2xl border border-brand-100 bg-surface-elevated/95 px-4 py-3 shadow-lg backdrop-blur-sm"
        role="region"
        aria-label="Cart summary"
      >
        <div class="min-w-0 flex-1">
          <p class="text-sm font-semibold text-ink">
            {{ itemLabel }} · {{ formatCurrency(cart.subtotal) }}
          </p>
          <p class="truncate text-xs text-ink-subtle">Ready when you are</p>
        </div>
        <NuxtLink
          to="/cart"
          class="shrink-0 rounded-lg border border-brand-200 px-3 py-2 text-sm font-medium text-brand-800 hover:bg-brand-50"
        >
          View cart
        </NuxtLink>
        <NuxtLink
          to="/checkout"
          class="shrink-0 rounded-lg bg-brand-700 px-3 py-2 text-sm font-medium text-white hover:bg-brand-800"
        >
          Checkout
        </NuxtLink>
      </div>
    </div>
  </Teleport>
</template>
