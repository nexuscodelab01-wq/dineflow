<script setup lang="ts">
import QRCode from 'qrcode'
import type { CardReader, DeviceKind, DevicePairResult, PosDevice } from '~/types/pos'
import type { StaffMember } from '~/types/staff'
import { fetchDevices, fetchReaders, pairDevice, registerReader, removeReader, revokeDevice, setStaffPin, updateDevicePrinter } from '~/services/pos'
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
  readers.value = await fetchReaders(admin.restaurantId).catch(() => [])
}

// ---- receipt printer per device ---------------------------------------------------------------------

const printerFor = ref<number | null>(null)
const printerForm = reactive({ host: '', port: 9100, cash_drawer: false, auto_print: false })
const savingPrinter = ref(false)

function editPrinter(device: PosDevice) {
  printerFor.value = device.id
  Object.assign(printerForm, { host: device.printer?.host ?? '', port: device.printer?.port ?? 9100, cash_drawer: device.printer?.cash_drawer ?? false, auto_print: device.printer?.auto_print ?? false })
}

async function savePrinter(device: PosDevice) {
  if (!admin.restaurantId) return
  savingPrinter.value = true
  try {
    await updateDevicePrinter(admin.restaurantId, device.id, { printer_host: printerForm.host.trim() || null, printer_port: Number(printerForm.port) || 9100, cash_drawer: printerForm.cash_drawer, auto_print: printerForm.auto_print })
    printerFor.value = null
    await load()
    ui.success('Printer saved')
  }
  catch (err) {
    ui.error(err instanceof Error ? err.message : 'Could not save the printer')
  }
  finally {
    savingPrinter.value = false
  }
}

// ---- smart card readers (WisePOS E / S700) -----------------------------------------------------------

const readers = ref<CardReader[]>([])
const readerCode = ref('')
const readerLabel = ref('')
const addingReader = ref(false)

async function addReader() {
  if (!admin.restaurantId || !readerCode.value.trim() || !readerLabel.value.trim()) return
  addingReader.value = true
  try {
    await registerReader(admin.restaurantId, readerCode.value, readerLabel.value)
    readerCode.value = ''
    readerLabel.value = ''
    await load()
    ui.success('Reader added')
  }
  catch (err) {
    ui.error(err instanceof Error ? err.message : 'Could not add that reader')
  }
  finally {
    addingReader.value = false
  }
}

async function dropReader(reader: CardReader) {
  if (!admin.restaurantId) return
  if (!await ui.confirm({ title: `Remove ${reader.label}?`, message: 'The till will stop offering it for card payments.', confirmLabel: 'Remove', destructive: true })) return
  try {
    await removeReader(admin.restaurantId, reader.id)
    await load()
  }
  catch (err) {
    ui.error(err instanceof Error ? err.message : 'Could not remove that reader')
  }
}

onMounted(async () => {
  await admin.initialize()
  await load()
  loading.value = false
})

// ---- pairing a device --------------------------------------------------------------------------------

const showForm = ref(false)
const label = ref('')
const kind = ref<DeviceKind>('TILL')
const pairing = ref(false)
const pairError = ref('')
const justPaired = ref<DevicePairResult | null>(null)
const pairQrCode = ref('')

async function submitPair() {
  if (!admin.restaurantId || pairing.value || !label.value.trim()) return
  pairing.value = true
  pairError.value = ''
  try {
    justPaired.value = await pairDevice(admin.restaurantId, label.value.trim(), kind.value)
    pairQrCode.value = await QRCode.toDataURL(justPaired.value.device_token, { margin: 1, width: 280, errorCorrectionLevel: 'M' })
    label.value = ''
    kind.value = 'TILL'
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
        <label class="block text-sm font-medium">Used as
          <select v-model="kind" class="mt-1 w-full rounded-lg border px-3 py-2 text-sm">
            <option value="TILL">Till — has a cash drawer</option>
            <option value="HANDHELD">Handheld — a server walks the floor with it</option>
          </select>
        </label>
        <AppButton type="submit" :disabled="pairing">{{ pairing ? 'Pairing…' : 'Pair device' }}</AppButton>
        <p v-if="pairError" class="w-full text-sm text-red-600" role="alert">{{ pairError }}</p>
      </form>

      <div v-if="justPaired" class="mt-4 rounded-2xl border border-amber-300 bg-amber-50 p-4">
        <p class="font-semibold text-amber-900">"{{ justPaired.label }}" paired — shown once, use it now:</p>
        <p class="mt-1 text-xs text-amber-800">Scan this on the iPad's Pairing screen in the DineFlow POS app (camera opens by default), or copy the code below if scanning isn't possible.</p>
        <img v-if="pairQrCode" :src="pairQrCode" alt="Pairing QR code" class="mt-3 h-40 w-40 rounded-lg border border-amber-200 bg-white p-2">
        <div class="mt-3 flex items-center gap-2">
          <code class="flex-1 break-all rounded-lg bg-white p-2 text-xs text-ink-muted">{{ justPaired.device_token }}</code>
          <button type="button" class="shrink-0 font-medium text-brand-700 hover:underline" @click="copyCode(justPaired.device_token)">Copy</button>
        </div>
        <button type="button" class="mt-3 text-xs text-amber-800 hover:underline" @click="justPaired = null; pairQrCode = ''">Dismiss</button>
      </div>

      <div v-if="loading" class="mt-6 h-32 animate-pulse rounded-2xl bg-brand-100/60" />
      <p v-else-if="!devices.length" class="mt-6 text-sm text-ink-subtle">No devices paired yet.</p>
      <ul v-else class="mt-4 space-y-3">
        <li v-for="device in devices" :key="device.id" class="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-brand-100 bg-surface-elevated p-4">
          <div>
            <div class="flex flex-wrap items-center gap-2">
              <span class="font-semibold text-ink">{{ device.label }}</span>
              <span class="rounded-full bg-sky-100 px-2 py-0.5 text-xs font-semibold text-sky-900">{{ device.kind === 'HANDHELD' ? 'Handheld' : 'Till' }}</span>
              <span v-if="device.revoked_at" class="rounded-full bg-brand-100 px-2 py-0.5 text-xs font-semibold text-brand-800">Revoked</span>
              <span v-else class="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-semibold text-emerald-900">Active</span>
            </div>
            <p class="mt-1 text-xs text-ink-subtle">
              Paired by {{ device.paired_by_label || 'unknown' }}
              <span v-if="device.last_seen_at"> · last used {{ new Date(device.last_seen_at).toLocaleString() }}</span>
            </p>
          </div>
          <div v-if="!device.revoked_at" class="flex gap-2">
            <button type="button" class="rounded-lg border border-brand-200 px-3 py-1.5 text-sm font-medium hover:bg-brand-50" @click="editPrinter(device)">
              {{ device.printer?.host ? 'Printer: ' + device.printer.host : 'Set up printer' }}
            </button>
            <button
              type="button"
              class="rounded-lg border border-red-300 px-3 py-1.5 text-sm font-medium text-red-700 hover:bg-red-50 disabled:opacity-60"
              :disabled="revokingId === device.id" @click="revoke(device)"
            >
              {{ revokingId === device.id ? 'Revoking…' : 'Revoke' }}
            </button>
          </div>
          <form v-if="printerFor === device.id" class="mt-3 grid w-full gap-3 sm:grid-cols-2" @submit.prevent="savePrinter(device)">
            <label class="block text-sm"><span class="text-ink-muted">Printer address (IP)</span>
              <input v-model="printerForm.host" class="mt-1 w-full rounded-lg border px-3 py-2 text-sm" placeholder="192.168.0.50 — blank to use AirPrint"></label>
            <label class="block text-sm"><span class="text-ink-muted">Port</span>
              <input v-model.number="printerForm.port" type="number" class="mt-1 w-full rounded-lg border px-3 py-2 text-sm"></label>
            <label class="flex items-center gap-2 text-sm"><input v-model="printerForm.cash_drawer" type="checkbox"> Cash drawer is plugged into this printer</label>
            <label class="flex items-center gap-2 text-sm"><input v-model="printerForm.auto_print" type="checkbox"> Print a receipt after every sale</label>
            <div class="flex gap-2 sm:col-span-2">
              <AppButton type="submit" :disabled="savingPrinter">{{ savingPrinter ? 'Saving…' : 'Save printer' }}</AppButton>
              <button type="button" class="text-sm text-ink-muted hover:underline" @click="printerFor = null">Cancel</button>
            </div>
          </form>
        </li>
      </ul>
    </section>

    <section class="mt-10">
      <h2 class="font-semibold">Card readers</h2>
      <p class="text-sm text-ink-muted">Smart readers (Stripe WisePOS E or S700) on your network. The till sends the amount; the customer taps or inserts their card — and picks a tip — on the reader itself. Requires Stripe to be connected.</p>
      <ul v-if="readers.length" class="mt-4 space-y-2">
        <li v-for="reader in readers" :key="reader.id" class="flex items-center justify-between rounded-2xl border border-brand-100 bg-surface-elevated p-4">
          <div>
            <span class="font-semibold text-ink">{{ reader.label }}</span>
            <span class="ml-2 text-xs text-ink-subtle">{{ reader.device_type }} · {{ reader.status }}</span>
          </div>
          <button type="button" class="text-sm text-red-700 hover:underline" @click="dropReader(reader)">Remove</button>
        </li>
      </ul>
      <form class="mt-4 grid gap-3 sm:grid-cols-3" @submit.prevent="addReader">
        <input v-model="readerCode" class="rounded-lg border px-3 py-2 text-sm" placeholder="Registration code from the reader">
        <input v-model="readerLabel" class="rounded-lg border px-3 py-2 text-sm" placeholder="Name, e.g. Counter">
        <AppButton type="submit" :disabled="addingReader">{{ addingReader ? 'Adding…' : 'Add reader' }}</AppButton>
      </form>
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
