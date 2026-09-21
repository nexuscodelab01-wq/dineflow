<template>
  <div
    class="flex min-h-screen flex-col bg-surface text-ink"
    :class="{ 'pb-24': showCartPad }"
  >
    <header class="border-b border-brand-100/80 bg-surface-elevated/80 backdrop-blur-sm">
      <div class="mx-auto flex max-w-6xl items-center justify-between px-4 py-4 sm:px-6">
        <NuxtLink to="/" class="font-display text-2xl font-semibold tracking-tight text-brand-800">
          DineFlow
        </NuxtLink>

        <button
          type="button"
          class="inline-flex items-center justify-center rounded-lg p-2 text-ink-muted hover:bg-brand-50 md:hidden"
          aria-label="Toggle navigation"
          @click="mobileOpen = !mobileOpen"
        >
          <span class="text-xl leading-none">{{ mobileOpen ? '×' : '☰' }}</span>
        </button>

        <nav class="hidden items-center gap-4 text-sm font-medium text-ink-muted md:flex">
          <NuxtLink to="/" class="hover:text-brand-700">Home</NuxtLink>
          <NuxtLink to="/menu" class="hover:text-brand-700">Menu</NuxtLink>
          <NuxtLink v-if="reservations" to="/reserve" class="hover:text-brand-700">Reserve</NuxtLink>
          <NuxtLink to="/cart" class="relative hover:text-brand-700">
            Cart
            <span
              v-if="cart.itemCount"
              class="absolute -right-3 -top-2 flex h-5 min-w-5 items-center justify-center rounded-full bg-brand-700 px-1 text-[10px] font-bold text-white"
            >
              {{ cart.itemCount }}
            </span>
          </NuxtLink>
          <template v-if="auth.isAuthenticated">
            <NuxtLink to="/orders" class="hover:text-brand-700">Orders</NuxtLink>
            <NuxtLink to="/profile" class="hover:text-brand-700">Profile</NuxtLink>
            <NuxtLink v-if="auth.isStaff" to="/admin" class="hover:text-brand-700">Admin</NuxtLink>
          </template>
          <template v-else>
            <NuxtLink to="/login" class="hover:text-brand-700">Sign in</NuxtLink>
            <NuxtLink
              to="/register"
              class="rounded-lg bg-brand-700 px-3 py-1.5 text-white hover:bg-brand-800"
            >
              Register
            </NuxtLink>
          </template>
        </nav>
      </div>

      <nav
        v-if="mobileOpen"
        class="border-t border-brand-100 px-4 py-4 md:hidden"
      >
        <div class="flex flex-col gap-2 text-sm font-medium text-ink-muted">
          <NuxtLink to="/" class="rounded-lg px-3 py-2 hover:bg-brand-50" @click="mobileOpen = false">Home</NuxtLink>
          <NuxtLink to="/menu" class="rounded-lg px-3 py-2 hover:bg-brand-50" @click="mobileOpen = false">Menu</NuxtLink>
          <NuxtLink v-if="reservations" to="/reserve" class="rounded-lg px-3 py-2 hover:bg-brand-50" @click="mobileOpen = false">Reserve</NuxtLink>
          <NuxtLink to="/cart" class="rounded-lg px-3 py-2 hover:bg-brand-50" @click="mobileOpen = false">
            Cart<span v-if="cart.itemCount"> ({{ cart.itemCount }})</span>
          </NuxtLink>
          <template v-if="auth.isAuthenticated">
            <NuxtLink to="/orders" class="rounded-lg px-3 py-2 hover:bg-brand-50" @click="mobileOpen = false">Orders</NuxtLink>
            <NuxtLink to="/profile" class="rounded-lg px-3 py-2 hover:bg-brand-50" @click="mobileOpen = false">Profile</NuxtLink>
            <NuxtLink v-if="auth.isStaff" to="/admin" class="rounded-lg px-3 py-2 hover:bg-brand-50" @click="mobileOpen = false">Admin</NuxtLink>
          </template>
          <template v-else>
            <NuxtLink to="/login" class="rounded-lg px-3 py-2 hover:bg-brand-50" @click="mobileOpen = false">Sign in</NuxtLink>
            <NuxtLink to="/register" class="rounded-lg px-3 py-2 hover:bg-brand-50" @click="mobileOpen = false">Register</NuxtLink>
          </template>
        </div>
      </nav>
    </header>

    <main class="flex-1">
      <slot />
    </main>

    <footer class="border-t border-brand-100/80 py-6 text-center text-sm text-ink-subtle">
      © {{ year }} DineFlow
    </footer>

    <FloatingCartBar />
  </div>
</template>

<script setup lang="ts">
const year = new Date().getFullYear()
const auth = useAuthStore()
const cart = useCartStore()
const reservations = useFeature('reservations')
const mobileOpen = ref(false)
const route = useRoute()

const hiddenCartBarRoutes = new Set(['/cart', '/checkout'])

const showCartPad = computed(() => {
  if (cart.isEmpty) return false
  const path = route.path.replace(/\/$/, '') || '/'
  return !hiddenCartBarRoutes.has(path)
})

watch(() => route.path, () => {
  mobileOpen.value = false
})
</script>
