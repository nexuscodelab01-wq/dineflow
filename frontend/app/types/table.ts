export type TableInfo = {
  restaurant_id: number
  restaurant_name: string
  table_number: string
  ordering_open: boolean
  reason?: string | null
}

export type JoinResponse = { access_token: string, session_id: number, guest_id: number }

export type SessionItem = {
  name: string
  quantity: number
  line_total: string
  special_instructions?: string | null
  options: string[]
}

export type SessionRound = {
  order_id: number
  order_number: string
  round_no: number | null
  status: string
  total: string
  ordered_by?: string | null
  created_at: string
  items: SessionItem[]
}

export type TableSessionView = {
  session_id: number
  restaurant_id: number
  restaurant_name: string
  table_number: string
  guests: string[]
  rounds: SessionRound[]
  total: string
  /** What this table has asked for and staff haven't answered yet: WAITER and/or BILL. */
  requests: string[]
}

export type QrTable = {
  table_id: number
  table_number: string
  zone?: string | null
  qr_token: string
  has_open_session: boolean
}

export type OpenTableSession = {
  session_id: number
  table_id: number
  table_number: string
  opened_at: string
  guests: number
  rounds: number
  total: string
  requests: string[]
}

export type ServiceRequest = {
  id: number
  session_id: number
  table_id: number
  table_number: string
  kind: 'WAITER' | 'BILL'
  asked_by?: string | null
  created_at: string
}
