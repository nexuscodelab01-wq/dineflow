<script setup lang="ts">
import type { StaffMember, StaffRole } from '~/types/staff'
import { fetchStaff, inviteStaff, resendStaffInvite, updateStaff } from '~/services/staff'

definePageMeta({ layout: 'admin', middleware: ['admin'] })

const admin = useAdminStore()
const auth = useAuthStore()
const ui = useUiStore()

const staff = ref<StaffMember[]>([])
const loading = ref(true)
const showForm = ref(false)
const creating = ref(false)
const formError = ref('')
const busyId = ref<number | null>(null)
const justInvited = ref<{ id: number, link: string } | null>(null)

const form = reactive({ email: '', first_name: '', last_name: '', role: 'RESTAURANT_STAFF' as StaffRole })

async function load() {
  if (!admin.restaurantId) return
  staff.value = await fetchStaff(admin.restaurantId)
}

onMounted(async () => {
  await admin.initialize()
  await load()
  loading.value = false
})

function resetForm() {
  Object.assign(form, { email: '', first_name: '', last_name: '', role: 'RESTAURANT_STAFF' })
  formError.value = ''
}

async function submit() {
  if (!admin.restaurantId || creating.value) return
  creating.value = true
  formError.value = ''
  try {
    const result = await inviteStaff(admin.restaurantId, { ...form })
    justInvited.value = { id: result.id, link: result.invite_link }
    resetForm()
    showForm.value = false
    await load()
  }
  catch (err) {
    formError.value = err instanceof Error ? err.message : 'Could not invite that person'
  }
  finally {
    creating.value = false
  }
}

async function toggleActive(member: StaffMember) {
  if (!admin.restaurantId || busyId.value) return
  busyId.value = member.id
  try {
    const updated = await updateStaff(admin.restaurantId, member.id, { is_active: !member.is_active })
    const i = staff.value.findIndex(s => s.id === member.id)
    if (i !== -1) staff.value[i] = updated
  }
  catch (err) {
    ui.error(err instanceof Error ? err.message : 'Could not update them')
  }
  finally {
    busyId.value = null
  }
}

async function changeRole(member: StaffMember, role: StaffRole) {
  if (!admin.restaurantId || busyId.value || role === member.role) return
  busyId.value = member.id
  try {
    const updated = await updateStaff(admin.restaurantId, member.id, { role })
    const i = staff.value.findIndex(s => s.id === member.id)
    if (i !== -1) staff.value[i] = updated
  }
  catch (err) {
    ui.error(err instanceof Error ? err.message : 'Could not change their role')
  }
  finally {
    busyId.value = null
  }
}

async function resend(member: StaffMember) {
  if (!admin.restaurantId || busyId.value) return
  busyId.value = member.id
  try {
    const { invite_link } = await resendStaffInvite(admin.restaurantId, member.id)
    justInvited.value = { id: member.id, link: invite_link }
  }
  catch (err) {
    ui.error(err instanceof Error ? err.message : 'Could not resend the invite')
  }
  finally {
    busyId.value = null
  }
}

function copyLink(link: string) {
  navigator.clipboard?.writeText(link).then(() => ui.success('Invite link copied')).catch(() => {})
}
</script>

<template>
  <div>
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="font-display text-2xl font-semibold text-brand-900">Staff</h1>
        <p class="text-sm text-ink-muted">Who can sign in to this restaurant's admin area</p>
      </div>
      <AppButton @click="showForm = !showForm">{{ showForm ? 'Close' : 'Invite someone' }}</AppButton>
    </div>

    <form v-if="showForm" class="mt-4 grid gap-3 rounded-2xl border border-brand-100 bg-surface-elevated p-5 sm:grid-cols-2" @submit.prevent="submit">
      <label class="block text-sm font-medium">First name
        <input v-model="form.first_name" required class="mt-1 w-full rounded-lg border px-3 py-2 text-sm" placeholder="Sam">
      </label>
      <label class="block text-sm font-medium">Last name
        <input v-model="form.last_name" required class="mt-1 w-full rounded-lg border px-3 py-2 text-sm" placeholder="Taylor">
      </label>
      <label class="block text-sm font-medium sm:col-span-2">Email
        <input v-model="form.email" type="email" required class="mt-1 w-full rounded-lg border px-3 py-2 text-sm" placeholder="sam@example.com">
      </label>
      <label class="block text-sm font-medium">Role
        <select v-model="form.role" class="mt-1 w-full rounded-lg border px-3 py-2 text-sm">
          <option value="RESTAURANT_STAFF">Staff</option>
          <option value="RESTAURANT_ADMIN">Admin</option>
        </select>
      </label>
      <p v-if="formError" class="text-sm text-red-600 sm:col-span-2" role="alert">{{ formError }}</p>
      <div class="sm:col-span-2">
        <AppButton type="submit" :disabled="creating">{{ creating ? 'Sending invite…' : 'Send invite' }}</AppButton>
      </div>
    </form>

    <div v-if="loading" class="mt-6 h-40 animate-pulse rounded-2xl bg-brand-100/60" />

    <p v-else-if="!staff.length" class="mt-8 text-sm text-ink-subtle">No one has been invited yet.</p>

    <ul v-else class="mt-6 space-y-3">
      <li v-for="member in staff" :key="member.id" class="rounded-2xl border border-brand-100 bg-surface-elevated p-4">
        <div class="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div class="flex flex-wrap items-center gap-2">
              <span class="font-semibold text-ink">{{ member.first_name }} {{ member.last_name }}</span>
              <span v-if="member.user_id === auth.user?.id" class="rounded-full bg-brand-50 px-2 py-0.5 text-xs font-medium text-brand-700">You</span>
              <span v-if="!member.is_active" class="rounded-full bg-brand-100 px-2 py-0.5 text-xs font-semibold text-brand-800">Deactivated</span>
              <span v-else-if="!member.invite_accepted" class="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-900">Invite pending</span>
            </div>
            <p class="mt-1 text-sm text-ink-muted">{{ member.email }}</p>
          </div>
          <div class="flex flex-wrap items-center gap-2">
            <select
              :value="member.role" class="rounded-lg border border-brand-200 px-2 py-1.5 text-sm"
              :disabled="busyId === member.id" @change="changeRole(member, ($event.target as HTMLSelectElement).value as StaffRole)"
            >
              <option value="RESTAURANT_STAFF">Staff</option>
              <option value="RESTAURANT_ADMIN">Admin</option>
            </select>
            <button
              v-if="!member.invite_accepted && member.is_active"
              type="button" class="rounded-lg border border-brand-200 px-3 py-1.5 text-sm font-medium hover:bg-brand-50"
              :disabled="busyId === member.id" @click="resend(member)"
            >
              Resend invite
            </button>
            <button
              type="button" class="rounded-lg border border-brand-200 px-3 py-1.5 text-sm font-medium hover:bg-brand-50"
              :disabled="busyId === member.id" @click="toggleActive(member)"
            >
              {{ member.is_active ? 'Deactivate' : 'Reactivate' }}
            </button>
          </div>
        </div>

        <div v-if="justInvited && justInvited.id === member.id" class="mt-3 rounded-lg bg-brand-50 p-3 text-xs">
          <p class="font-semibold text-brand-800">Invite link (shown once — copy it now):</p>
          <div class="mt-1 flex items-center gap-2">
            <code class="flex-1 truncate text-ink-muted">{{ justInvited.link }}</code>
            <button type="button" class="shrink-0 font-medium text-brand-700 hover:underline" @click="copyLink(justInvited.link)">Copy</button>
          </div>
        </div>
      </li>
    </ul>
  </div>
</template>
