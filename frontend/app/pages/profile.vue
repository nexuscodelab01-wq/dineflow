<template>
  <div class="mx-auto max-w-2xl px-4 py-12 sm:px-6">
    <div class="rounded-2xl border border-brand-100 bg-surface-elevated p-8 shadow-sm">
      <p class="text-sm font-semibold uppercase tracking-[0.2em] text-brand-600">
        Account
      </p>
      <h1 class="font-display mt-2 text-3xl font-semibold text-brand-900">
        Profile
      </h1>

      <div v-if="hydrated && auth.user" class="mt-8 space-y-4">
        <div class="grid gap-4 sm:grid-cols-2">
          <div class="rounded-xl bg-surface-muted/60 p-4">
            <p class="text-xs uppercase tracking-wide text-ink-subtle">Name</p>
            <p class="mt-1 font-medium text-ink">{{ auth.fullName }}</p>
          </div>
          <div class="rounded-xl bg-surface-muted/60 p-4">
            <p class="text-xs uppercase tracking-wide text-ink-subtle">Email</p>
            <p class="mt-1 font-medium text-ink">{{ auth.user.email }}</p>
          </div>
          <div class="rounded-xl bg-surface-muted/60 p-4">
            <p class="text-xs uppercase tracking-wide text-ink-subtle">Phone</p>
            <p class="mt-1 font-medium text-ink">{{ auth.user.phone || '—' }}</p>
          </div>
          <div class="rounded-xl bg-surface-muted/60 p-4">
            <p class="text-xs uppercase tracking-wide text-ink-subtle">Role</p>
            <p class="mt-1 font-medium text-ink">{{ auth.user.role.name }}</p>
          </div>
        </div>

        <form class="rounded-xl border border-brand-100 p-4" @submit.prevent="submitChange">
          <h2 class="font-semibold text-ink">Change password</h2>
          <div class="mt-3 grid gap-3 sm:grid-cols-2">
            <label class="block text-sm font-medium sm:col-span-2">Current password
              <input v-model="current" type="password" required autocomplete="current-password" class="mt-1 w-full rounded-lg border border-brand-200 px-3 py-2 text-sm">
            </label>
            <label class="block text-sm font-medium">New password
              <input v-model="next" type="password" required minlength="8" autocomplete="new-password" class="mt-1 w-full rounded-lg border border-brand-200 px-3 py-2 text-sm">
            </label>
            <label class="block text-sm font-medium">Type it again
              <input v-model="again" type="password" required autocomplete="new-password" class="mt-1 w-full rounded-lg border border-brand-200 px-3 py-2 text-sm">
            </label>
          </div>
          <p v-if="again && next !== again" class="mt-2 text-xs text-red-600">The two new passwords do not match.</p>
          <p v-if="changeError" class="mt-2 text-sm text-red-600" role="alert">{{ changeError }}</p>
          <p v-if="changed" class="mt-2 text-sm text-emerald-700" role="status">Password changed. Your other devices have been signed out.</p>
          <AppButton type="submit" class="mt-3" :disabled="changing || (again !== '' && next !== again)">{{ changing ? 'Saving…' : 'Change password' }}</AppButton>
        </form>

        <div class="flex flex-wrap gap-3 pt-4">
          <AppButton @click="handleLogout">
            Sign out
          </AppButton>
          <NuxtLink
            v-if="auth.isStaff"
            to="/admin"
            class="inline-flex items-center rounded-lg border border-brand-200 px-4 py-2 text-sm font-semibold text-brand-800 hover:bg-brand-50"
          >
            Admin area
          </NuxtLink>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { changePassword, storeTokens } from '~/services/auth'

definePageMeta({ middleware: ['auth'] })

const auth = useAuthStore()
const router = useRouter()
const hydrated = useHydrated()

const current = ref('')
const next = ref('')
const again = ref('')
const changing = ref(false)
const changed = ref(false)
const changeError = ref('')

async function submitChange() {
  if (changing.value || next.value !== again.value) return
  changing.value = true
  changed.value = false
  changeError.value = ''
  try {
    storeTokens(await changePassword(current.value, next.value)) // this device stays signed in with fresh tokens
    current.value = next.value = again.value = ''
    changed.value = true
  }
  catch (err) {
    changeError.value = err instanceof Error ? err.message : 'Could not change the password'
  }
  finally {
    changing.value = false
  }
}

async function handleLogout() {
  await auth.logout()
  await router.push('/login')
}
</script>
