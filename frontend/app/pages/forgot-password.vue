<script setup lang="ts">
import { forgotPassword } from '~/services/auth'

const restaurant = useRestaurantStore()
const email = ref('')
const sending = ref(false)
const sent = ref(false)
const error = ref('')

async function submit() {
  if (sending.value) return
  sending.value = true
  error.value = ''
  try {
    const current = await restaurant.load()
    await forgotPassword(email.value.trim(), current?.id ?? null)
    sent.value = true // the same message whether or not the address has an account
  }
  catch (err) {
    error.value = err instanceof Error ? err.message : 'Something went wrong. Please try again.'
  }
  finally {
    sending.value = false
  }
}
</script>

<template>
  <div class="mx-auto flex min-h-[70vh] max-w-md flex-col justify-center px-4 py-12 sm:px-6">
    <div class="rounded-2xl border border-brand-100 bg-surface-elevated p-8 shadow-sm">
      <h1 class="font-display text-3xl font-semibold text-brand-900">Forgot your password?</h1>

      <div v-if="sent" class="mt-6 space-y-4" role="status">
        <p class="text-ink">If <strong>{{ email }}</strong> has an account, we have sent a link to choose a new password. It works once and expires in an hour.</p>
        <p class="text-sm text-ink-muted">Nothing arrived? Check your spam folder, or try again in a few minutes.</p>
        <NuxtLink to="/login" class="inline-block text-sm font-semibold text-brand-700 hover:text-brand-800">← Back to sign in</NuxtLink>
      </div>

      <form v-else class="mt-6 space-y-4" @submit.prevent="submit">
        <p class="text-sm text-ink-muted">Enter your email and we will send you a link to choose a new one.</p>
        <div>
          <label class="mb-1 block text-sm font-medium text-ink" for="forgot-email">Email</label>
          <input id="forgot-email" v-model="email" type="email" required autocomplete="email" class="w-full rounded-lg border border-brand-200 bg-white px-3 py-2 text-sm outline-none ring-brand-500 focus:ring-2">
        </div>
        <p v-if="error" class="text-sm text-red-600">{{ error }}</p>
        <AppButton type="submit" class="w-full" :disabled="sending">{{ sending ? 'Sending…' : 'Send me a link' }}</AppButton>
        <p class="text-center text-sm"><NuxtLink to="/login" class="font-medium text-brand-700 hover:text-brand-800">Back to sign in</NuxtLink></p>
      </form>
    </div>
  </div>
</template>
