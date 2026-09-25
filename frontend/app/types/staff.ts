export type StaffRole = 'RESTAURANT_ADMIN' | 'RESTAURANT_STAFF'

export type StaffMember = {
  id: number // the membership id — what you act on
  user_id: number
  email: string
  first_name: string
  last_name: string
  role: StaffRole
  is_active: boolean
  created_at: string
  invite_accepted: boolean
}

export type StaffInvitePayload = {
  email: string
  first_name: string
  last_name: string
  role: StaffRole
}

export type StaffInviteResult = StaffMember & {
  invite_link: string
}
