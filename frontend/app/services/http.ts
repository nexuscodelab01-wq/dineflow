import { ApiError, parseApiErrorBody } from '~/utils/api-error'

const ACCESS_TOKEN_KEY = 'dineflow_access_token'

export function getApiBaseUrl(): string {
  const config = useRuntimeConfig()
  // During SSR in Docker, call the backend service hostname — not localhost.
  if (import.meta.server) {
    return (config.apiUrl as string) || (config.public.apiUrl as string)
  }
  return config.public.apiUrl as string
}

function getAccessToken(): string | null {
  if (import.meta.server) return null
  return localStorage.getItem(ACCESS_TOKEN_KEY)
}

export async function apiFetch<T>(
  path: string,
  options: RequestInit & { auth?: boolean } = {},
): Promise<T> {
  const base = getApiBaseUrl()
  const headers = new Headers(options.headers)
  if (!headers.has('Content-Type') && options.body) {
    headers.set('Content-Type', 'application/json')
  }

  if (options.auth !== false) {
    const token = getAccessToken()
    if (token) headers.set('Authorization', `Bearer ${token}`)
  }

  let response: Response
  try {
    response = await fetch(`${base}${path}`, { ...options, headers })
  }
  catch {
    throw new ApiError('Unable to reach the server. Check your connection and try again.', 0)
  }

  if (!response.ok) {
    let body: unknown = null
    try {
      body = await response.json()
    }
    catch { /* ignore */ }

    const error = parseApiErrorBody(body, response.status)

    if (error.isUnauthorized && import.meta.client) {
      const auth = useAuthStore()
      if (auth.isAuthenticated) {
        await auth.logout()
      }
    }

    throw error
  }

  if (response.status === 204) return undefined as T
  return await response.json() as T
}

export { ApiError }
