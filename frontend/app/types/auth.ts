export type RoleName =
  | 'CUSTOMER'
  | 'RESTAURANT_ADMIN'
  | 'RESTAURANT_STAFF'
  | 'SUPER_ADMIN'

export type Role = {
  id: number
  name: RoleName
  description?: string | null
}

export type User = {
  restaurant_id?: number | null
  id: number
  email: string
  first_name: string
  last_name: string
  phone?: string | null
  is_active: boolean
  role: Role
}

export type TokenResponse = {
  access_token: string
  refresh_token: string
  token_type: string
}

export type LoginPayload = {
  email: string
  password: string
  /** The restaurant site being signed in to (omit for platform-level sign-in). */
  restaurant_id?: number | null
}

export type RegisterPayload = {
  restaurant_id: number
  email: string
  password: string
  first_name: string
  last_name: string
  phone?: string
}

export type ApiErrorBody = {
  detail?: string | { msg?: string }[]
}
