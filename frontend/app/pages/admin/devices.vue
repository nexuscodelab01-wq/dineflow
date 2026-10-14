<script setup lang="ts">
import type { DevicePairResult, PosDevice } from '~/types/pos'
import type { StaffMember } from '~/types/staff'
import { fetchDevices, pairDevice, revokeDevice, setStaffPin } from '~/services/pos'
import { fetchStaff } from '~/services/staff'

definePageMeta({ layout: 'admin', middleware: ['admin'] })

const admin = useAdminStore()
const ui = useUiStore()

const devices = ref<PosDevice[]>([])
const staff = ref<StaffMember[]>([])
const loading = ref(true)

async function load() {
  if (!admin.restaurantId) return
  ;[devices.value, staff.value] = await Promise.all([fetchDevices(admin.restaurantId), fetchStaff(admin.restaurantId)])
}

onMounted(async () => {
  await admin.initialize()
  await load()
  loading.value = false
})

// ---- pairing a device --------------------------------------------------------------------------------

const showForm = ref(false)
const label = ref('')
const pairing = ref(false)
const pairError = ref('')
const justPaired = ref<DevicePairResult | null>(null)

async function submitPair() {
  if (!admin.restaurantId || pairing.value || !label.value.trim()) return
  pairing.value = true
  pairError.value = ''
  try {
    justPaired.value = await pairDevice(admin.restaurantId, label.value.trim())
    label.value = ''
    showForm.value = false
    await load()
  }
  catch (err) {
    pairError.value = err instanceof Error ? err.message : 'Could not pair that device'
  }
  finally {
    pairing.value = false
  }
}

const revokingId = ref<number | null>(null)

async function revoke(device: PosDevice) {
  if (!admin.restaurantId || revokingId.value) return
  const ok = await ui.confirm({
    title: `Revoke "${device.label}"?`,
    message: 'This iPad will be signed out immediately — any order in progress on it will stop working. Pairing it again needs a new code.',
    confirmLabel: 'Revoke device',
    destructive: true,
  })
  if (!ok) return
  revokingId.value = device.id
  try {
    await revokeDevice(admin.restaurantId, device.id)
    await load()
    ui.success(`"${device.label}" revoked`)
  }
  catch (err) {
    ui.error(err instanceof Error ? err.message : 'Could not revoke that device')
  }
  finally {
    revokingId.value = null
  }
}

function copyCode(code: string) {
  navigator.clipboard?.writeText(code).then(() => ui.success('Pairing code copied')).catch(() => {})
}

// ---- staff PINs ----------------------------------------------------------------------------------------

const pinFormFor = ref<number | null>(null)
const pinValue = ref('')
const settingPin = ref(false)
const pinError = ref('')

function startPin(member: StaffMember) {
  pinFormFor.value = member.id
  pinValue.value = ''
  pinError.value = ''
}

async function submitPin(member: StaffMember) {
  if (!admin.restaurantId || settingPin.value || pinValue.value.length < 4) return
  settingPin.value = true
  pinError.value = ''
  try {
    await setStaffPin(admin.restaurantId, member.id, pinValue.value)
    pinFormFor.value = null
    ui.success(`PIN set for ${member.first_name}`)
  }
  catch (err) {
    pinError.value = err instanceof Error ? err.message : 'Could not set that PIN'
  }
  finally {
    settingPin.value = false
  }
}
</script>

<template>
  <div>
    <div>
      <h1 class="font-display text-2xl font-semibold text-brand-900">POS devices</h1>
      <p class="text-sm text-ink-muted">Pair an iPad as a till, and set staff PINs for quick-switching on it.</p>
    </div>

    <section class="mt-6">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <h2 class="font-semibold">Paired devices</h2>
        <AppButton @click="showForm = !showForm">{{ showForm ? 'Close' : 'Pair a device' }}</AppButton>
      </div>

      <form v-if="showForm" class="mt-4 flex flex-wrap items-end gap-3 rounded-2xl border border-brand-100 bg-surface-elevated p-5" @submit.prevent="submitPair">
        <label class="block text-sm font-medium">Label
          <input v-model="label" required class="mt-1 w-full rounded-lg border px-3 py-2 text-sm" placeholder="Front counter iPad">
        </label>
        <AppButton type="submit" :disabled="pairing">{{ pairing ? 'Pairing…' : 'Pair device' }}</AppButton>
        <p v-if="pairError" class="w-full text-sm text-red-600" role="alert">{{ pairError }}</p>
      </form>

      <div v-if="justPaired" class="mt-4 rounded-2xl border border-amber-300 bg-amber-50 p-4">
        <p class="font-semibold text-amber-900">"{{ justPaired.label }}" paired — shown once, copy it now:</p>
        <p class="mt-1 text-xs text-amber-800">Enter this on the iPad's Pairing screen in the DineFlow POS app.</p>
        <div class="mt-2 flex items-center gap-2">
          <code class="flex-1 break-all rounded-lg bg-white p-2 text-xs text-ink-muted">{{ justPaired.device_token }}</code>
          <button type="button" class="shrink-0 font-medium text-brand-700 hover:underline" @click="copyCode(justPaired.device_token)">Copy</button>
        </div>
        <button type="button" class="mt-3 text-xs text-amber-800 hover:underline" @click="justPaired = null">Dismiss</button>
      </div>

      <div v-if="loading" class="mt-6 h-32 animate-pulse rounded-2xl bg-brand-100/60" />
      <p v-else-if="!devices.length" class="mt-6 text-sm text-ink-subtle">No devices paired yet.</p>
      <ul v-else class="mt-4 space-y-3">
        <li v-for="device in devices" :key="device.id" class="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-brand-100 bg-surface-elevated p-4">
          <div>
            <div class="flex flex-wrap items-center gap-2">
              <span class="font-semibold text-ink">{{ device.label }}</span>
              <span v-if="device.revoked_at" class="rounded-full bg-brand-100 px-2 py-0.5 text-xs font-semibold text-brand-800">Revoked</span>
              <span v-else class="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-semibold text-emerald-900">Active</span>
            </div>
            <p class="mt-1 text-xs text-ink-subtle">
              Paired by {{ device.paired_by_label || 'unknown' }}
              <span v-if="device.last_seen_at"> · last used {{ new Date(device.last_seen_at).toLocaleString() }}</span>
            </p>
          </div>
          <button
            v-if="!device.revoked_at" type="button"
            class="rounded-lg border border-red-300 px-3 py-1.5 text-sm font-medium text-red-700 hover:bg-red-50 disabled:opacity-60"
            :disabled="revokingId === device.id" @click="revoke(device)"
          >
            {{ revokingId === device.id ? 'Revoking…' : 'Revoke' }}
          </button>
        </li>
      </ul>
    </section>

    <section class="mt-10">
      <h2 class="font-semibold">Staff PINs</h2>
      <p class="text-sm text-ink-muted">A quick-switch PIN lets someone log into a paired device without a full sign-in. Unique per restaurant.</p>

      <ul v-if="staff.length" class="mt-4 space-y-3">
        <li v-for="member in staff" :key="member.id" class="rounded-2xl border border-brand-100 bg-surface-elevated p-4">
          <div class="flex flex-wrap items-center justify-between gap-3">
            <div>
              <span class="font-semibold text-ink">{{ member.first_name }} {{ member.last_name }}</span>
              <span class="ml-2 text-xs text-ink-subtle">{{ member.email }}</span>
            </div>
            <button
              v-if="pinFormFor !== member.id" type="button"
              class="rounded-lg border border-brand-200 px-3 py-1.5 text-sm font-medium hover:bg-brand-50"
              @click="startPin(member)"
            >
              Set PIN
            </button>
          </div>
          <form v-if="pinFormFor === member.id" class="mt-3 flex flex-wrap items-end gap-3" @submit.prevent="submitPin(member)">
            <label class="block text-sm font-medium">New PIN (4–8 digits)
              <input
                v-model="pinValue" type="text" inputmode="numeric" pattern="[0-9]*" minlength="4" maxlength="8" required
                class="mt-1 w-32 rounded-lg border px-3 py-2 text-sm"
              >
            </label>
            <AppButton type="submit" :disabled="settingPin">{{ settingPin ? 'Saving…' : 'Save PIN' }}</AppButton>
            <button type="button" class="text-sm text-ink-subtle hover:underline" @click="pinFormFor = null">Cancel</button>
            <p v-if="pinError" class="w-full text-sm text-red-600" role="alert">{{ pinError }}</p>
          </form>
        </li>
      </ul>
    </section>
  </div>
</template>
