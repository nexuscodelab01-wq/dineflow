export type PosDevice = {
  id: number
  label: string
  paired_by_label: string | null
  revoked_at: string | null
  last_seen_at: string | null
  created_at: string
}

export type DevicePairResult = {
  device_id: number
  label: string
  device_token: string // shown once — the pairing code
}
