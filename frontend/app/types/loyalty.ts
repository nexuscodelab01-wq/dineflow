export type LoyaltyReason = 'EARNED' | 'REDEEMED' | 'ADJUSTED'

export type LoyaltyTransaction = {
  id: number
  order_id?: number | null
  points: number
  reason: LoyaltyReason
  note?: string | null
  created_at: string
}

export type LoyaltyAccount = {
  balance: number
  points_per_currency: number
  transactions: LoyaltyTransaction[]
}

export type AdminLoyaltyAccount = {
  user_id: number
  name: string
  email: string
  balance: number
}
