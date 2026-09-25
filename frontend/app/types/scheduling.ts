export type PickupSlot = {
  at: string
  /** null = no per-slot cap set by the restaurant. */
  remaining: number | null
}

export type PickupSlots = {
  date: string
  /** The restaurant's own zone — label the times in it, not the visitor's. */
  timezone: string
  days_ahead: number
  interval_minutes: number
  slots: PickupSlot[]
}
