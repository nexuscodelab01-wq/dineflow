<template>
  <div class="min-h-screen flex flex-col bg-surface text-ink">
    <header class="border-b border-brand-100/80 bg-surface-elevated/80 backdrop-blur-sm">
      <div class="mx-auto flex max-w-6xl items-center justify-between px-4 py-4 sm:px-6">
        <NuxtLink to="/" class="font-display text-2xl font-semibold tracking-tight text-brand-800">
          DineFlow
        </NuxtLink>
        <nav class="flex items-center gap-4 text-sm font-medium text-ink-muted">
          <NuxtLink to="/" class="hover:text-brand-700">Home</NuxtLink>
          <NuxtLink to="/menu" class="hover:text-brand-700">Menu</NuxtLink>
          <template v-if="auth.isAuthenticated">
            <NuxtLink to="/profile" class="hover:text-brand-700">Profile</NuxtLink>
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
    </header>

    <main class="flex-1">
      <slot />
    </main>

    <footer class="border-t border-brand-100/80 py-6 text-center text-sm text-ink-subtle">
      © {{ year }} DineFlow
    </footer>
  </div>
</template>

<script setup lang="ts">
const year = new Date().getFullYear()
const auth = useAuthStore()
</script>
