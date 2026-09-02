<script setup lang="ts">
import { formatCurrency } from '~/utils/format'

const cart = useCartStore()
const restaurant = useRestaurantStore()
const router = useRouter()

onMounted(() => restaurant.load())
</script>

<template>
  <div class="mx-auto max-w-3xl px-4 py-8 sm:px-6">
    <h1 class="font-display text-3xl font-semibold text-brand-900">Your cart</h1>

    <div v-if="cart.isEmpty" class="mt-10 rounded-2xl border border-dashed border-brand-200 py-16 text-center">
      <p class="text-ink-muted">Your cart is empty.</p>
      <NuxtLink to="/menu" class="mt-4 inline-block font-semibold text-brand-700 hover:text-brand-800">
        Browse menu
      </NuxtLink>
    </div>

    <div v-else class="mt-6 space-y-4">
      <article
        v-for="line in cart.lines"
        :key="line.id"
        class="rounded-2xl border border-brand-100 bg-surface-elevated p-4"
      >
        <div class="flex items-start justify-between gap-4">
          <div>
            <h2 class="font-semibold text-ink">{{ line.name }}</h2>
            <ul v-if="line.modifiers.length" class="mt-1 space-y-0.5 text-sm text-ink-muted">
              <li v-for="mod in line.modifiers" :key="mod.option_id">
                {{ mod.modifier_name }}: {{ mod.option_name }}
              </li>
            </ul>
            <p v-if="line.special_instructions" class="mt-1 text-sm italic text-ink-subtle">
              "{{ line.special_instructions }}"
            </p>
          </div>
          <p class="font-semibold text-brand-800">{{ formatCurrency(line.unit_price * line.quantity) }}</p>
        </div>
        <div class="mt-4 flex items-center justify-between">
          <div class="flex items-center gap-2">
            <button class="h-8 w-8 rounded-lg border border-brand-200" @click="cart.updateQuantity(line.id, line.quantity - 1)">−</button>
            <span class="w-8 text-center text-sm font-medium">{{ line.quantity }}</span>
            <button class="h-8 w-8 rounded-lg border border-brand-200" @click="cart.updateQuantity(line.id, line.quantity + 1)">+</button>
          </div>
          <button class="text-sm text-red-600 hover:text-red-700" @click="cart.removeLine(line.id)">Remove</button>
        </div>
      </article>

      <div v-if="restaurant.current" class="rounded-2xl border border-brand-100 bg-brand-50/50 p-4 text-sm">
        <div class="flex justify-between"><span>Subtotal</span><span>{{ formatCurrency(cart.computeTotals(restaurant.current, 'PICKUP').subtotal) }}</span></div>
        <p class="mt-2 text-xs text-ink-subtle">Tax and fees calculated at checkout.</p>
      </div>

      <div class="flex flex-wrap gap-3">
        <AppButton @click="router.push('/checkout')">Proceed to checkout</AppButton>
        <NuxtLink to="/menu" class="inline-flex items-center rounded-lg border border-brand-200 px-4 py-2 text-sm font-semibold text-brand-800">
          Continue shopping
        </NuxtLink>
      </div>
    </div>
  </div>
</template>
