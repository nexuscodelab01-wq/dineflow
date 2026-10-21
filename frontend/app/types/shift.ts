export type ShiftReportRead = {
  shift_id: number
  opened_at: string
  opened_by: string | null
  closed_at: string | null
  closed_by: string | null
  starting_float: string
  cash_total: string
  card_total: string
  order_count: number
  expected_cash: string
  counted_cash: string | null
  variance: string | null
  card_tips: string
  cash_tips: string
}

export type EmployeeReportRow = {
  user_id: number
  name: string
  cash_total: string
  card_total: string
  order_count: number
  hours_worked: string
  sales_per_labour_hour: string | null
  card_tips: string
  cash_tips: string
}
