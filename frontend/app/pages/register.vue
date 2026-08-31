<template>
  <div class="mx-auto flex min-h-[70vh] max-w-md flex-col justify-center px-4 py-12 sm:px-6">
    <div class="rounded-2xl border border-brand-100 bg-surface-elevated p-8 shadow-sm">
      <h1 class="font-display text-3xl font-semibold text-brand-900">
        Create account
      </h1>
      <p class="mt-2 text-sm text-ink-muted">
        Join DineFlow to order and track meals
      </p>

      <form class="mt-8 space-y-4" @submit.prevent="handleSubmit">
        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="mb-1 block text-sm font-medium text-ink" for="first_name">First name</label>
            <input
              id="first_name"
              v-model="form.first_name"
              required
              class="w-full rounded-lg border border-brand-200 bg-white px-3 py-2 text-sm outline-none ring-brand-500 focus:ring-2"
            >
          </div>
          <div>
            <label class="mb-1 block text-sm font-medium text-ink" for="last_name">Last name</label>
            <input
              id="last_name"
              v-model="form.last_name"
              required
              class="w-full rounded-lg border border-brand-200 bg-white px-3 py-2 text-sm outline-none ring-brand-500 focus:ring-2"
            >
          </div>
        </div>
        <div>
          <label class="mb-1 block text-sm font-medium text-ink" for="email">Email</label>
          <input
            id="email"
            v-model="form.email"
            type="email"
            required
            class="w-full rounded-lg border border-brand-200 bg-white px-3 py-2 text-sm outline-none ring-brand-500 focus:ring-2"
          >
        </div>
        <div>
          <label class="mb-1 block text-sm font-medium text-ink" for="phone">Phone (optional)</label>
          <input
            id="phone"
            v-model="form.phone"
            type="tel"
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
            minlength="8"
            class="w-full rounded-lg border border-brand-200 bg-white px-3 py-2 text-sm outline-none ring-brand-500 focus:ring-2"
          >
        </div>

        <p v-if="error" class="text-sm text-red-600">
          {{ error }}
        </p>

        <AppButton type="submit" class="w-full" :disabled="auth.loading">
          {{ auth.loading ? 'Creating account…' : 'Create account' }}
        </AppButton>
      </form>

      <p class="mt-6 text-center text-sm text-ink-muted">
        Already have an account?
        <NuxtLink to="/login" class="font-semibold text-brand-700 hover:text-brand-800">
          Sign in
        </NuxtLink>
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
definePageMeta({ middleware: ['guest'] })

const auth = useAuthStore()

const form = reactive({
  email: '',
  password: '',
  first_name: '',
  last_name: '',
  phone: '',
})
const error = ref('')

async function handleSubmit() {
  error.value = ''
  try {
    await auth.register({
      ...form,
      phone: form.phone || undefined,
    })
    await navigateTo('/profile')
  }
  catch (err) {
    error.value = err instanceof Error ? err.message : 'Registration failed'
  }
}
</script>
