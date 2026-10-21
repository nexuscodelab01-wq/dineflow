// TILL owns a cash drawer (mandatory shift + float); HANDHELD is carried by a server and has none.
export type DeviceKind = 'TILL' | 'HANDHELD'

export type DevicePrinter = { host: string | null, port: number, cash_drawer: boolean, auto_print: boolean }

export type CardReader = { id: string, label: string, status: string, device_type: string | null, test_mode?: boolean }

export type PosDevice = {
  id: number
  label: string
  kind: DeviceKind
  printer: DevicePrinter
  paired_by_label: string | null
  revoked_at: string | null
  last_seen_at: string | null
  created_at: string
}

export type DevicePairResult = {
  device_id: number
  label: string
  kind: DeviceKind
  device_token: string // shown once — the pairing code
}
