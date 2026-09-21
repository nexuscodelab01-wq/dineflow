<script setup lang="ts">
import { resetPassword } from '~/services/auth'

const route = useRoute()
const token = computed(() => (typeof route.query.token === 'string' ? route.query.token : ''))
const password = ref('')
const confirm = ref('')
const saving = ref(false)
const done = ref(false)
const error = ref('')

const mismatch = computed(() => confirm.value.length > 0 && password.value !== confirm.value)

async function submit() {
  if (saving.value || mismatch.value) return
  saving.value = true
  error.value = ''
  try {
    await resetPassword(token.value, password.value)
    done.value = true
  }
  catch (err) {
    error.value = err instanceof Error ? err.message : 'Something went wrong. Please try again.'
  }
  finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="mx-auto flex min-h-[70vh] max-w-md flex-col justify-center px-4 py-12 sm:px-6">
    <div class="rounded-2xl border border-brand-100 bg-surface-elevated p-8 shadow-sm">
      <h1 class="font-display text-3xl font-semibold text-brand-900">Choose a new password</h1>

      <div v-if="!token" class="mt-6 space-y-3">
        <p class="text-ink">This page needs the link from your email.</p>
        <NuxtLink to="/forgot-password" class="text-sm font-semibold text-brand-700">Ask for a new link</NuxtLink>
      </div>

      <div v-else-if="done" class="mt-6 space-y-4" role="status">
        <p class="text-ink">Your password has been changed. You can sign in with it now.</p>
        <NuxtLink to="/login" class="inline-flex items-center rounded-lg bg-brand-700 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-800">Sign in</NuxtLink>
      </div>

      <form v-else class="mt-6 space-y-4" @submit.prevent="submit">
        <div>
          <label class="mb-1 block text-sm font-medium text-ink" for="new-password">New password</label>
          <input id="new-password" v-model="password" type="password" required minlength="8" autocomplete="new-password" class="w-full rounded-lg border border-brand-200 bg-white px-3 py-2 text-sm outline-none ring-brand-500 focus:ring-2">
          <p class="mt-1 text-xs text-ink-subtle">At least 8 characters with a letter and a number, and nothing too common.</p>
        </div>
        <div>
          <label class="mb-1 block text-sm font-medium text-ink" for="confirm-password">Type it again</label>
          <input id="confirm-password" v-model="confirm" type="password" required autocomplete="new-password" class="w-full rounded-lg border border-brand-200 bg-white px-3 py-2 text-sm outline-none ring-brand-500 focus:ring-2">
          <p v-if="mismatch" class="mt-1 text-xs text-red-600">The two passwords do not match.</p>
        </div>
        <p v-if="error" class="text-sm text-red-600" role="alert">
          {{ error }}
          <NuxtLink v-if="/invalid|expired/i.test(error)" to="/forgot-password" class="ml-1 font-semibold underline">Get a new link</NuxtLink>
        </p>
        <AppButton type="submit" class="w-full" :disabled="saving || mismatch">{{ saving ? 'Saving…' : 'Change password' }}</AppButton>
      </form>
    </div>
  </div>
</template>
