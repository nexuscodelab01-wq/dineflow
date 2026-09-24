<template>
  <div
    class="flex min-h-screen flex-col bg-surface text-ink"
    :class="{ 'pb-24': showCartPad }"
  >
    <header class="border-b border-brand-100/80 bg-surface-elevated/80 backdrop-blur-sm">
      <div class="mx-auto flex max-w-6xl items-center justify-between px-4 py-4 sm:px-6">
        <NuxtLink to="/" class="font-display text-2xl font-semibold tracking-tight text-brand-800">
          <img v-if="branding.logo.value" :src="branding.logo.value" :alt="branding.name.value ?? 'Home'" class="h-10 w-auto max-w-[12rem] object-contain">
          <template v-else>{{ branding.name.value ?? 'DineFlow' }}</template>
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
          <NuxtLink to="/" class="hover:text-brand-700" :class="{ 'font-semibold text-brand-700': isActive('/') }" :aria-current="isActive('/') ? 'page' : undefined">Home</NuxtLink>
          <NuxtLink to="/menu" class="hover:text-brand-700" :class="{ 'font-semibold text-brand-700': isActive('/menu') }" :aria-current="isActive('/menu') ? 'page' : undefined">Menu</NuxtLink>
          <NuxtLink v-if="reservations" to="/reserve" class="hover:text-brand-700" :class="{ 'font-semibold text-brand-700': isActive('/reserve') }" :aria-current="isActive('/reserve') ? 'page' : undefined">Reserve</NuxtLink>
          <NuxtLink to="/cart" class="relative hover:text-brand-700" :class="{ 'font-semibold text-brand-700': isActive('/cart') }" :aria-current="isActive('/cart') ? 'page' : undefined">
            Cart
            <span
              v-if="cartCount"
              class="absolute -right-3 -top-2 flex h-5 min-w-5 items-center justify-center rounded-full bg-brand-700 px-1 text-[10px] font-bold text-white"
            >
              {{ cartCount }}
            </span>
          </NuxtLink>
          <template v-if="signedIn">
            <NuxtLink to="/orders" class="hover:text-brand-700" :class="{ 'font-semibold text-brand-700': isActive('/orders') }" :aria-current="isActive('/orders') ? 'page' : undefined">Orders</NuxtLink>
            <NuxtLink v-if="reviewsEnabled" to="/reviews" class="hover:text-brand-700" :class="{ 'font-semibold text-brand-700': isActive('/reviews') }" :aria-current="isActive('/reviews') ? 'page' : undefined">Reviews</NuxtLink>
            <NuxtLink to="/profile" class="hover:text-brand-700" :class="{ 'font-semibold text-brand-700': isActive('/profile') }" :aria-current="isActive('/profile') ? 'page' : undefined">Profile</NuxtLink>
            <NuxtLink v-if="staffIn" to="/admin" class="hover:text-brand-700" :class="{ 'font-semibold text-brand-700': isActive('/admin') }" :aria-current="isActive('/admin') ? 'page' : undefined">Admin</NuxtLink>
            <NuxtLink v-if="platformIn" to="/platform" class="hover:text-brand-700" :class="{ 'font-semibold text-brand-700': isActive('/platform') }" :aria-current="isActive('/platform') ? 'page' : undefined">Platform</NuxtLink>
          </template>
          <template v-else>
            <NuxtLink to="/login" class="hover:text-brand-700" :class="{ 'font-semibold text-brand-700': isActive('/login') }" :aria-current="isActive('/login') ? 'page' : undefined">Sign in</NuxtLink>
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
          <NuxtLink to="/" class="rounded-lg px-3 py-2 hover:bg-brand-50" :class="{ 'bg-brand-50 font-semibold text-brand-700': isActive('/') }" :aria-current="isActive('/') ? 'page' : undefined" @click="mobileOpen = false">Home</NuxtLink>
          <NuxtLink to="/menu" class="rounded-lg px-3 py-2 hover:bg-brand-50" :class="{ 'bg-brand-50 font-semibold text-brand-700': isActive('/menu') }" :aria-current="isActive('/menu') ? 'page' : undefined" @click="mobileOpen = false">Menu</NuxtLink>
          <NuxtLink v-if="reservations" to="/reserve" class="rounded-lg px-3 py-2 hover:bg-brand-50" :class="{ 'bg-brand-50 font-semibold text-brand-700': isActive('/reserve') }" :aria-current="isActive('/reserve') ? 'page' : undefined" @click="mobileOpen = false">Reserve</NuxtLink>
          <NuxtLink to="/cart" class="rounded-lg px-3 py-2 hover:bg-brand-50" :class="{ 'bg-brand-50 font-semibold text-brand-700': isActive('/cart') }" :aria-current="isActive('/cart') ? 'page' : undefined" @click="mobileOpen = false">
            Cart<span v-if="cartCount"> ({{ cartCount }})</span>
          </NuxtLink>
          <template v-if="signedIn">
            <NuxtLink to="/orders" class="rounded-lg px-3 py-2 hover:bg-brand-50" :class="{ 'bg-brand-50 font-semibold text-brand-700': isActive('/orders') }" :aria-current="isActive('/orders') ? 'page' : undefined" @click="mobileOpen = false">Orders</NuxtLink>
            <NuxtLink v-if="reviewsEnabled" to="/reviews" class="rounded-lg px-3 py-2 hover:bg-brand-50" :class="{ 'bg-brand-50 font-semibold text-brand-700': isActive('/reviews') }" :aria-current="isActive('/reviews') ? 'page' : undefined" @click="mobileOpen = false">Reviews</NuxtLink>
            <NuxtLink to="/profile" class="rounded-lg px-3 py-2 hover:bg-brand-50" :class="{ 'bg-brand-50 font-semibold text-brand-700': isActive('/profile') }" :aria-current="isActive('/profile') ? 'page' : undefined" @click="mobileOpen = false">Profile</NuxtLink>
            <NuxtLink v-if="staffIn" to="/admin" class="rounded-lg px-3 py-2 hover:bg-brand-50" :class="{ 'bg-brand-50 font-semibold text-brand-700': isActive('/admin') }" :aria-current="isActive('/admin') ? 'page' : undefined" @click="mobileOpen = false">Admin</NuxtLink>
            <NuxtLink v-if="platformIn" to="/platform" class="rounded-lg px-3 py-2 hover:bg-brand-50" :class="{ 'bg-brand-50 font-semibold text-brand-700': isActive('/platform') }" :aria-current="isActive('/platform') ? 'page' : undefined" @click="mobileOpen = false">Platform</NuxtLink>
          </template>
          <template v-else>
            <NuxtLink to="/login" class="rounded-lg px-3 py-2 hover:bg-brand-50" :class="{ 'bg-brand-50 font-semibold text-brand-700': isActive('/login') }" :aria-current="isActive('/login') ? 'page' : undefined" @click="mobileOpen = false">Sign in</NuxtLink>
            <NuxtLink to="/register" class="rounded-lg px-3 py-2 hover:bg-brand-50" @click="mobileOpen = false">Register</NuxtLink>
          </template>
        </div>
      </nav>
    </header>

    <main class="flex-1">
      <slot />
    </main>

    <footer class="border-t border-brand-100/80 py-6 text-center text-sm text-ink-subtle">
      © {{ year }} {{ branding.name.value ?? 'DineFlow' }}
    </footer>

    <FloatingCartBar />
  </div>
</template>

<script setup lang="ts">
const year = new Date().getFullYear()
const auth = useAuthStore()
const cart = useCartStore()
const reservations = useFeature('reservations')
const reviewsEnabled = useFeature('reviews')
const branding = useBranding()
const mobileOpen = ref(false)
const route = useRoute()

// Who is signed in and what is in the cart live in the browser, so the server cannot draw them. Both sides draw the
// signed-out header first and it is filled in once the page is live; drawing them differently made the browser keep
// the server's link targets under the wrong labels.
const ready = ref(false)
onMounted(() => { ready.value = true })
const signedIn = computed(() => ready.value && auth.isAuthenticated)
const staffIn = computed(() => ready.value && auth.isStaff)
const platformIn = computed(() => ready.value && auth.isPlatformAdmin)
const cartCount = computed(() => (ready.value ? cart.itemCount : 0))

const hiddenCartBarRoutes = new Set(['/cart', '/checkout'])

// "/" only matches the home page itself; every other link also covers its own sub-pages
// (e.g. "/orders" stays active on "/orders/42") so a detail page still shows where you are.
function isActive(path: string): boolean {
  if (path === '/') return route.path === '/'
  return route.path === path || route.path.startsWith(`${path}/`)
}

const showCartPad = computed(() => {
  if (!ready.value || cart.isEmpty) return false
  const path = route.path.replace(/\/$/, '') || '/'
  return !hiddenCartBarRoutes.has(path)
})

watch(() => route.path, () => {
  mobileOpen.value = false
})
</script>
