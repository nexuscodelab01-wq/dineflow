import type {
  LoginPayload,
  RegisterPayload,
  TokenResponse,
  User,
} from '~/types/auth'
import { apiFetch, getApiBaseUrl } from '~/services/http'
import { ACCESS_TOKEN_KEY, REFRESH_TOKEN_KEY } from '~/utils/session-refresh'

export { apiFetch, getApiBaseUrl }

export function getStoredAccessToken(): string | null {
  if (import.meta.server) return null
  return localStorage.getItem(ACCESS_TOKEN_KEY)
}

export function getStoredRefreshToken(): string | null {
  if (import.meta.server) return null
  return localStorage.getItem(REFRESH_TOKEN_KEY)
}

export function storeTokens(tokens: TokenResponse): void {
  localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access_token)
  localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token)
}

export function clearStoredTokens(): void {
  localStorage.removeItem(ACCESS_TOKEN_KEY)
  localStorage.removeItem(REFRESH_TOKEN_KEY)
}

export async function login(payload: LoginPayload): Promise<TokenResponse> {
  return apiFetch<TokenResponse>('/api/v1/auth/login', {
    method: 'POST',
    body: JSON.stringify(payload),
    auth: false,
  })
}

export async function register(payload: RegisterPayload): Promise<TokenResponse> {
  return apiFetch<TokenResponse>('/api/v1/auth/register', {
    method: 'POST',
    body: JSON.stringify(payload),
    auth: false,
  })
}

export async function refreshTokens(): Promise<TokenResponse> {
  const refreshToken = getStoredRefreshToken()
  if (!refreshToken) throw new Error('No refresh token')

  return apiFetch<TokenResponse>('/api/v1/auth/refresh', {
    method: 'POST',
    body: JSON.stringify({ refresh_token: refreshToken }),
    auth: false,
  })
}

export async function logoutRequest(): Promise<void> {
  const refreshToken = getStoredRefreshToken()
  if (!refreshToken) return

  await apiFetch('/api/v1/auth/logout', {
    method: 'POST',
    body: JSON.stringify({ refresh_token: refreshToken }),
    auth: false,
  })
}

export async function fetchCurrentUser(): Promise<User> {
  return apiFetch<User>('/api/v1/auth/me')
}

export async function forgotPassword(email: string, restaurantId: number | null): Promise<{ message: string }> {
  return apiFetch<{ message: string }>('/api/v1/auth/forgot-password', {
    method: 'POST',
    body: JSON.stringify({ email, restaurant_id: restaurantId }),
    auth: false,
  })
}

export async function resetPassword(token: string, password: string): Promise<{ message: string }> {
  return apiFetch<{ message: string }>('/api/v1/auth/reset-password', {
    method: 'POST',
    body: JSON.stringify({ token, password }),
    auth: false,
  })
}

/** Changes the password while signed in. Every other session is signed out; this one gets fresh tokens. */
export async function changePassword(currentPassword: string, newPassword: string): Promise<TokenResponse> {
  return apiFetch<TokenResponse>('/api/v1/auth/change-password', {
    method: 'POST',
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  })
}
