<template>
  <div class="mx-auto flex min-h-[70vh] max-w-md flex-col justify-center px-4 py-12 sm:px-6">
    <div class="rounded-2xl border border-brand-100 bg-surface-elevated p-8 shadow-sm">
      <h1 class="font-display text-3xl font-semibold text-brand-900">
        Sign in
      </h1>
      <p class="mt-2 text-sm text-ink-muted">
        Access your DineFlow account
      </p>

      <form class="mt-8 space-y-4" @submit.prevent="handleSubmit">
        <div>
          <label class="mb-1 block text-sm font-medium text-ink" for="email">Email</label>
          <input
            id="email"
            v-model="form.email"
            type="email"
            required
            autocomplete="email"
            class="w-full rounded-lg border border-brand-200 bg-white px-3 py-2 text-sm outline-none ring-brand-500 focus:ring-2"
          >
        </div>
        <div>
          <label class="mb-1 block text-sm font-medium text-ink" for="password">Password</label>
          <input
            id="password"
            v-model="form.password"
            type="password"
            required
            autocomplete="current-password"
            class="w-full rounded-lg border border-brand-200 bg-white px-3 py-2 text-sm outline-none ring-brand-500 focus:ring-2"
          >
        </div>

        <p v-if="error" class="text-sm text-red-600">
          {{ error }}
        </p>

        <AppButton type="submit" class="w-full" :disabled="auth.loading">
          {{ auth.loading ? 'Signing in…' : 'Sign in' }}
        </AppButton>
      </form>

      <p class="mt-6 text-center text-sm text-ink-muted">
        No account?
        <NuxtLink to="/register" class="font-semibold text-brand-700 hover:text-brand-800">
          Create one
        </NuxtLink>
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
definePageMeta({ middleware: ['guest'] })

const auth = useAuthStore()
const restaurant = useRestaurantStore()
const route = useRoute()

const form = reactive({
  email: '',
  password: '',
})
const error = ref('')

async function handleSubmit() {
  error.value = ''
  try {
    await restaurant.load()
    await auth.login({ ...form, restaurant_id: restaurant.id })
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/profile'
    await navigateTo(redirect)
  }
  catch (err) {
    error.value = err instanceof Error ? err.message : 'Login failed'
  }
}
</script>
