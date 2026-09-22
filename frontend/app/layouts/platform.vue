<script setup lang="ts">
const auth = useAuthStore()
const router = useRouter()
const loggingOut = ref(false)

async function handleLogout() {
  if (loggingOut.value) return
  loggingOut.value = true
  try {
    await auth.logout()
    await router.push('/login')
  }
  finally {
    loggingOut.value = false
  }
}
</script>

<template>
  <div class="min-h-screen bg-surface text-ink">
    <header class="border-b border-brand-100 bg-surface-elevated">
      <div class="mx-auto flex max-w-5xl items-center justify-between px-4 py-4 sm:px-6">
        <div>
          <NuxtLink to="/platform" class="font-display text-xl font-semibold text-brand-900">DineFlow Platform</NuxtLink>
          <p class="text-xs text-ink-subtle">Signed in as {{ auth.user?.email }}</p>
        </div>
        <button class="rounded-lg border border-brand-200 px-3 py-1.5 text-sm font-medium text-red-700 hover:bg-red-50" :disabled="loggingOut" @click="handleLogout">
          {{ loggingOut ? 'Signing out…' : 'Log out' }}
        </button>
      </div>
    </header>
    <main class="mx-auto max-w-5xl px-4 py-8 sm:px-6">
      <slot />
    </main>
  </div>
</template>
