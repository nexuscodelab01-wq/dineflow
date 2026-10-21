export type TipRow = {
  user_id: number
  name: string
  card_tips: string
  cash_tips: string
  collected: string
  hours: string
  payout: string
}

export type TipReport = {
  mode: 'KEEP' | 'POOL_EQUAL' | 'POOL_HOURS'
  start: string
  end: string
  total: string
  /** Online tips (delivery / pickup) with no server to credit. */
  unassigned?: string
  rows: TipRow[]
  already_finalized: boolean
}

export type TipAllocation = {
  id: number
  user_id: number
  name: string
  period_start: string
  period_end: string
  mode: string
  collected: string
  amount: string
  hours: string
  created_at: string
}
