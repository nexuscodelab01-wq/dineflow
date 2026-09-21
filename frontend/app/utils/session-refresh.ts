/**
 * Silent session refresh.
 *
 * Access tokens are short-lived (30 min). When an authenticated request comes back 401 we swap the
 * refresh token for a new pair and retry once, so staff on a shared tablet aren't thrown to the
 * login screen mid-shift. Framework-free so it can be unit tested.
 */

export const ACCESS_TOKEN_KEY = 'dineflow_access_token'
export const REFRESH_TOKEN_KEY = 'dineflow_refresh_token'

type KeyValueStorage = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>

export type RefreshDeps = {
  baseUrl: string
  storage: KeyValueStorage
  fetchImpl?: typeof fetch
}

let inflight: Promise<boolean> | null = null

/** For tests. */
export function resetRefreshState() {
  inflight = null
}

/**
 * Exchange the stored refresh token for a new pair. Resolves true when the session is usable
 * again. Concurrent callers share one network request: refresh tokens rotate, so a second
 * parallel refresh with the same token would fail and wrongly sign the user out.
 */
export function refreshSession(deps: RefreshDeps): Promise<boolean> {
  inflight ??= doRefresh(deps).finally(() => {
    inflight = null
  })
  return inflight
}

async function doRefresh({ baseUrl, storage, fetchImpl = fetch }: RefreshDeps): Promise<boolean> {
  const used = storage.getItem(REFRESH_TOKEN_KEY)
  if (!used) return false

  let response: Response
  try {
    response = await fetchImpl(`${baseUrl}/api/v1/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: used }),
    })
  }
  catch {
    return false // offline / server down: keep the session, the caller will surface the error
  }

  if (response.ok) {
    const tokens = await response.json() as { access_token: string, refresh_token: string }
    storage.setItem(ACCESS_TOKEN_KEY, tokens.access_token)
    storage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token)
    return true
  }

  // Rate limited or a server hiccup: not a verdict on the session, so don't sign anyone out.
  if (response.status === 429 || response.status >= 500) return false

  // Rejected. Another tab may have rotated the token a moment ago — then we're fine.
  if (storage.getItem(REFRESH_TOKEN_KEY) !== used) return true

  storage.removeItem(ACCESS_TOKEN_KEY)
  storage.removeItem(REFRESH_TOKEN_KEY)
  return false
}
