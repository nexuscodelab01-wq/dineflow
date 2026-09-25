import { ApiError, parseApiErrorBody } from '~/utils/api-error'
import { ACCESS_TOKEN_KEY, refreshSession } from '~/utils/session-refresh'

/** For the Nuxt server's *own* outgoing requests (apiFetch during SSR) — the internal Docker hostname
 * when there is one, since that's faster and doesn't round-trip through the public port mapping.
 * Never use this for a URL that ends up in rendered markup (an `<img src>`, a `<link href>`, a JSON-LD
 * `image` field…) — the browser has to fetch that itself, and it cannot resolve an internal-only
 * hostname like `backend:8000`. Use `getPublicApiBaseUrl()` for those; see resolveMediaUrl. */
export function getApiBaseUrl(): string {
  const config = useRuntimeConfig()
  // During SSR in Docker, call the backend service hostname — not localhost.
  if (import.meta.server) {
    return (config.apiUrl as string) || (config.public.apiUrl as string)
  }
  return config.public.apiUrl as string
}

/** The API's address as the *browser* can reach it — same on client and server. Anything embedded in
 * markup (image/link URLs) must use this, not getApiBaseUrl(), or the server-rendered HTML points at
 * an address only the Nuxt server's own network can resolve (masked in normal use once client-side
 * hydration silently repaints it with the right URL — but broken for a crawler, a share-link preview
 * bot, or anyone viewing the page source, and a real flash of missing images before hydration). */
export function getPublicApiBaseUrl(): string {
  return useRuntimeConfig().public.apiUrl as string
}

function getAccessToken(): string | null {
  if (import.meta.server) return null
  return localStorage.getItem(ACCESS_TOKEN_KEY)
}

export async function apiFetch<T>(
  path: string,
  options: RequestInit & { auth?: boolean, retried?: boolean } = {},
): Promise<T> {
  const { retried, ...fetchOptions } = options
  const base = getApiBaseUrl()
  const headers = new Headers(options.headers)
  const isFormData = typeof FormData !== 'undefined' && options.body instanceof FormData
  if (!headers.has('Content-Type') && options.body && !isFormData) {
    headers.set('Content-Type', 'application/json')
  }

  if (options.auth !== false) {
    const token = getAccessToken()
    if (token) headers.set('Authorization', `Bearer ${token}`)
  }

  let response: Response
  try {
    response = await fetch(`${base}${path}`, { ...fetchOptions, headers })
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

    // Expired access token: quietly get a new one and replay the request once.
    if (error.isUnauthorized && options.auth !== false && !retried && import.meta.client) {
      if (await refreshSession({ baseUrl: base, storage: localStorage })) {
        return apiFetch<T>(path, { ...options, retried: true })
      }
    }

    // Calls that carry their own credentials (login, a table pass) must not sign out a customer's separate account.
    if (error.isUnauthorized && options.auth !== false && import.meta.client) {
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

/** For a non-JSON download (a CSV export, say). Shares auth/refresh/error handling with `apiFetch`,
 * but returns the raw Blob instead of parsing a body that was never JSON. */
export async function apiFetchBlob(path: string, options: RequestInit & { retried?: boolean } = {}): Promise<Blob> {
  const { retried, ...fetchOptions } = options
  const base = getApiBaseUrl()
  const headers = new Headers(options.headers)
  const token = getAccessToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)

  let response: Response
  try {
    response = await fetch(`${base}${path}`, { ...fetchOptions, headers })
  }
  catch {
    throw new ApiError('Unable to reach the server. Check your connection and try again.', 0)
  }

  if (!response.ok) {
    let body: unknown = null
    try {
      body = await response.json()
    }
    catch { /* ignore — most failures here are plain-text or empty */ }
    const error = parseApiErrorBody(body, response.status)
    if (error.isUnauthorized && !retried && import.meta.client && await refreshSession({ baseUrl: base, storage: localStorage })) {
      return apiFetchBlob(path, { ...options, retried: true })
    }
    throw error
  }

  return await response.blob()
}

export { ApiError }
