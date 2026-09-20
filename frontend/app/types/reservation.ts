export type ReservationStatus =
  | 'HELD'
  | 'CONFIRMED'
  | 'SEATED'
  | 'COMPLETED'
  | 'CANCELLED'
  | 'EXPIRED'

export type Reservation = {
  id: number
  restaurant_id: number
  table_id: number
  table_number?: string | null
  table_capacity?: number | null
  user_id?: number | null
  order_id?: number | null
  party_size: number
  starts_at: string
  ends_at: string
  status: ReservationStatus
  hold_expires_at?: string | null
  guest_name: string
  guest_email?: string | null
  guest_phone?: string | null
  notes?: string | null
  created_at: string
  /** Minutes a seated party has stayed past their booked end (0 = on time). */
  overdue_minutes?: number
  /** Name of the seated party still at this booking's table when it is due. */
  blocked_by?: string | null
}

export type AvailableTable = {
  id: number
  table_number: string
  capacity: number
  zone?: string | null
  status: string
}

/** A table on the customer seating plan, with its state for the searched time. */
export type FloorTable = {
  id: number
  table_number: string
  capacity: number
  zone?: string | null
  shape?: 'ROUND' | 'SQUARE' | 'RECT'
  pos_x?: number | null
  pos_y?: number | null
  /** AVAILABLE, UNAVAILABLE (taken at that time) or TOO_SMALL (for the party). */
  state: 'AVAILABLE' | 'UNAVAILABLE' | 'TOO_SMALL'
}

export type AvailabilityResponse = {
  starts_at: string
  ends_at: string
  party_size: number
  tables: AvailableTable[]
  /** Every active table with its state, for drawing the seating plan. */
  floor: FloorTable[]
  /** Nearby start times with a free table; only present when `tables` is empty. */
  suggested_times: string[]
}

export type ReservationConflict = {
  id: number
  guest_name: string
  party_size: number
  starts_at: string
  ends_at: string
  status: ReservationStatus
}

/** Slot status for a requested time — not the table's status right now. */
export type SlotStatus = 'AVAILABLE' | 'RESERVED' | 'OCCUPIED' | 'CLEANING' | 'TOO_SMALL'

export type AdminTableAvailability = {
  id: number
  table_number: string
  capacity: number
  zone?: string | null
  shape?: 'ROUND' | 'SQUARE' | 'RECT'
  pos_x?: number | null
  pos_y?: number | null
  floor_status: string
  slot_status: SlotStatus
  available: boolean
  conflicts: ReservationConflict[]
}

export type AdminAvailabilityResponse = {
  starts_at: string
  ends_at: string
  party_size: number
  tables: AdminTableAvailability[]
}

export type TableReservationBrief = {
  id: number
  guest_name: string
  guest_phone?: string | null
  party_size: number
  starts_at: string
  ends_at: string
  status: ReservationStatus
  /** True when this booking is why the table is RESERVED/OCCUPIED right now. */
  blocking: boolean
  overdue_minutes?: number
}

export type UpdateReservationPayload = Partial<{
  table_id: number
  party_size: number
  starts_at: string
  duration_minutes: number
  guest_name: string
  guest_email: string
  guest_phone: string
  notes: string
}>

export type CreateReservationPayload = {
  table_id: number
  party_size: number
  starts_at: string
  duration_minutes?: number
  guest_name: string
  guest_email?: string
  guest_phone?: string
  notes?: string
  hold?: boolean
}
