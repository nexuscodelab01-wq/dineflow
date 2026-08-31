<template>
  <div class="mx-auto max-w-2xl px-4 py-12 sm:px-6">
    <div class="rounded-2xl border border-brand-100 bg-surface-elevated p-8 shadow-sm">
      <p class="text-sm font-semibold uppercase tracking-[0.2em] text-brand-600">
        Account
      </p>
      <h1 class="font-display mt-2 text-3xl font-semibold text-brand-900">
        Profile
      </h1>

      <div v-if="auth.user" class="mt-8 space-y-4">
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
definePageMeta({ middleware: ['auth'] })

const auth = useAuthStore()
const router = useRouter()

async function handleLogout() {
  await auth.logout()
  await router.push('/login')
}
</script>
