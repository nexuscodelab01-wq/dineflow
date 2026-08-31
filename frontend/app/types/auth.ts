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
}

export type RegisterPayload = {
  email: string
  password: string
  first_name: string
  last_name: string
  phone?: string
}

export type ApiErrorBody = {
  detail?: string | { msg?: string }[]
}
