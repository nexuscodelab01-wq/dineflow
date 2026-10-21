export type Adjustment = {
  id: number
  kind: 'VOID' | 'COMP' | 'DISCOUNT' | 'REFUND'
  amount: string
  reason_code: string
  note: string | null
  order_number: string | null
  staff: string | null
  authorized_by: string | null
  created_at: string
  detail: Record<string, unknown>
}
