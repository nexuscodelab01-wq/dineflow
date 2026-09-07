<script setup lang="ts">
const auth = useAuthStore()
const admin = useAdminStore()
await admin.initialize()

const mobileOpen = ref(false)
const route = useRoute()

const nav = [
  { to: '/admin', label: 'Dashboard' },
  { to: '/admin/menu', label: 'Menu' },
  { to: '/admin/orders', label: 'Orders' },
  { to: '/admin/kitchen', label: 'Kitchen' },
  { to: '/admin/tables', label: 'Tables' },
  { to: '/admin/customers', label: 'Customers' },
  { to: '/admin/settings', label: 'Settings' },
]

watch(() => route.path, () => {
  mobileOpen.value = false
})
</script>

<template>
  <div class="min-h-screen bg-surface-muted/40">
    <header class="border-b border-brand-100 bg-surface-elevated">
      <div class="mx-auto flex max-w-7xl items-center justify-between px-4 py-4 sm:px-6">
        <div>
          <NuxtLink to="/admin" class="font-display text-xl font-semibold text-brand-900">DineFlow Admin</NuxtLink>
          <p v-if="admin.restaurant" class="text-xs text-ink-subtle">{{ admin.restaurant.name }}</p>
        </div>
        <div class="flex items-center gap-3 text-sm">
          <button
            type="button"
            class="rounded-lg p-2 text-ink-muted hover:bg-brand-50 lg:hidden"
            aria-label="Toggle admin navigation"
            @click="mobileOpen = !mobileOpen"
          >
            <span class="text-xl leading-none">{{ mobileOpen ? '×' : '☰' }}</span>
          </button>
          <NuxtLink to="/" class="hidden text-ink-muted hover:text-brand-700 sm:inline">Storefront</NuxtLink>
          <span class="hidden text-ink-subtle sm:inline">{{ auth.fullName }}</span>
        </div>
      </div>

      <nav
        v-if="mobileOpen"
        class="border-t border-brand-100 px-4 py-3 lg:hidden"
      >
        <div class="flex flex-col gap-1">
          <NuxtLink
            v-for="item in nav"
            :key="item.to"
            :to="item.to"
            class="rounded-lg px-3 py-2 text-sm font-medium text-ink-muted hover:bg-brand-50 hover:text-brand-800"
            active-class="bg-brand-100 text-brand-900"
          >
            {{ item.label }}
          </NuxtLink>
        </div>
      </nav>
    </header>

    <div class="mx-auto flex max-w-7xl gap-6 px-4 py-6 sm:px-6">
      <aside class="hidden w-52 shrink-0 lg:block">
        <nav class="space-y-1">
          <NuxtLink
            v-for="item in nav"
            :key="item.to"
            :to="item.to"
            class="block rounded-lg px-3 py-2 text-sm font-medium text-ink-muted hover:bg-brand-50 hover:text-brand-800"
            active-class="bg-brand-100 text-brand-900"
          >
            {{ item.label }}
          </NuxtLink>
        </nav>
      </aside>
      <main class="min-w-0 flex-1">
        <slot />
      </main>
    </div>
  </div>
</template>
