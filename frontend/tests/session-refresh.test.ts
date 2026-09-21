import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  ACCESS_TOKEN_KEY,
  REFRESH_TOKEN_KEY,
  refreshSession,
  resetRefreshState,
} from '../app/utils/session-refresh'

function memoryStorage(initial: Record<string, string> = {}) {
  const data = new Map(Object.entries(initial))
  return {
    getItem: (k: string) => data.get(k) ?? null,
    setItem: (k: string, v: string) => void data.set(k, v),
    removeItem: (k: string) => void data.delete(k),
  }
}

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status })

describe('refreshSession', () => {
  beforeEach(() => resetRefreshState())

  it('stores the rotated token pair on success', async () => {
    const storage = memoryStorage({ [ACCESS_TOKEN_KEY]: 'old-a', [REFRESH_TOKEN_KEY]: 'old-r' })
    const fetchImpl = vi.fn().mockResolvedValue(json({ access_token: 'new-a', refresh_token: 'new-r' }))

    expect(await refreshSession({ baseUrl: 'http://api', storage, fetchImpl })).toBe(true)
    expect(storage.getItem(ACCESS_TOKEN_KEY)).toBe('new-a')
    expect(storage.getItem(REFRESH_TOKEN_KEY)).toBe('new-r')
    expect(fetchImpl).toHaveBeenCalledWith('http://api/api/v1/auth/refresh', expect.objectContaining({
      body: JSON.stringify({ refresh_token: 'old-r' }),
    }))
  })

  it('shares one request between concurrent callers (refresh tokens rotate)', async () => {
    const storage = memoryStorage({ [REFRESH_TOKEN_KEY]: 'r1' })
    const fetchImpl = vi.fn().mockImplementation(async () => {
      await new Promise(r => setTimeout(r, 10))
      return json({ access_token: 'a2', refresh_token: 'r2' })
    })
    const results = await Promise.all([1, 2, 3].map(() => refreshSession({ baseUrl: 'http://api', storage, fetchImpl })))
    expect(results).toEqual([true, true, true])
    expect(fetchImpl).toHaveBeenCalledTimes(1)
  })

  it('fails without a refresh token, without calling the server', async () => {
    const fetchImpl = vi.fn()
    expect(await refreshSession({ baseUrl: 'http://api', storage: memoryStorage(), fetchImpl })).toBe(false)
    expect(fetchImpl).not.toHaveBeenCalled()
  })

  it('clears the session when the refresh token is rejected', async () => {
    const storage = memoryStorage({ [ACCESS_TOKEN_KEY]: 'a', [REFRESH_TOKEN_KEY]: 'revoked' })
    const fetchImpl = vi.fn().mockResolvedValue(json({ detail: 'Invalid or expired refresh token' }, 401))
    expect(await refreshSession({ baseUrl: 'http://api', storage, fetchImpl })).toBe(false)
    expect(storage.getItem(ACCESS_TOKEN_KEY)).toBeNull()
    expect(storage.getItem(REFRESH_TOKEN_KEY)).toBeNull()
  })

  it('accepts a rotation done by another tab instead of signing out', async () => {
    const storage = memoryStorage({ [REFRESH_TOKEN_KEY]: 'stale' })
    const fetchImpl = vi.fn().mockImplementation(async () => {
      storage.setItem(REFRESH_TOKEN_KEY, 'fresh-from-other-tab') // the other tab wins the race
      return json({ detail: 'Invalid or expired refresh token' }, 401)
    })
    expect(await refreshSession({ baseUrl: 'http://api', storage, fetchImpl })).toBe(true)
    expect(storage.getItem(REFRESH_TOKEN_KEY)).toBe('fresh-from-other-tab')
  })

  it('keeps the session on rate limits, server errors and network failures', async () => {
    for (const impl of [
      vi.fn().mockResolvedValue(json({}, 429)),
      vi.fn().mockResolvedValue(json({}, 503)),
      vi.fn().mockRejectedValue(new TypeError('offline')),
    ]) {
      resetRefreshState()
      const storage = memoryStorage({ [ACCESS_TOKEN_KEY]: 'a', [REFRESH_TOKEN_KEY]: 'r' })
      expect(await refreshSession({ baseUrl: 'http://api', storage, fetchImpl: impl })).toBe(false)
      expect(storage.getItem(REFRESH_TOKEN_KEY)).toBe('r')
    }
  })
})

describe('apiFetch with expired access tokens', () => {
  const logout = vi.fn()

  beforeEach(() => {
    resetRefreshState()
    logout.mockReset()
    localStorage.clear()
    vi.stubGlobal('useRuntimeConfig', () => ({ apiUrl: 'http://api', public: { apiUrl: 'http://api' } }))
    vi.stubGlobal('useAuthStore', () => ({ isAuthenticated: true, logout }))
  })

  it('refreshes once and replays the request', async () => {
    const { apiFetch } = await import('../app/services/http')
    localStorage.setItem(ACCESS_TOKEN_KEY, 'expired')
    localStorage.setItem(REFRESH_TOKEN_KEY, 'r1')
    const seen: string[] = []
    vi.stubGlobal('fetch', vi.fn().mockImplementation(async (url: string, init: RequestInit) => {
      const auth = new Headers(init.headers).get('Authorization')
      if (url.endsWith('/auth/refresh')) return json({ access_token: 'fresh', refresh_token: 'r2' })
      seen.push(String(auth))
      return auth === 'Bearer fresh' ? json({ ok: true }) : json({ detail: 'Invalid access token' }, 401)
    }))

    expect(await apiFetch<{ ok: boolean }>('/api/v1/orders')).toEqual({ ok: true })
    expect(seen).toEqual(['Bearer expired', 'Bearer fresh'])
    expect(logout).not.toHaveBeenCalled()
  })

  it('signs out when the session cannot be refreshed', async () => {
    const { apiFetch } = await import('../app/services/http')
    localStorage.setItem(ACCESS_TOKEN_KEY, 'expired')
    localStorage.setItem(REFRESH_TOKEN_KEY, 'revoked')
    vi.stubGlobal('fetch', vi.fn().mockImplementation(async (url: string) =>
      url.endsWith('/auth/refresh') ? json({ detail: 'nope' }, 401) : json({ detail: 'Invalid access token' }, 401)))

    await expect(apiFetch('/api/v1/orders')).rejects.toMatchObject({ status: 401 })
    expect(logout).toHaveBeenCalledTimes(1)
  })

  it('does not loop when the replayed request is still rejected', async () => {
    const { apiFetch } = await import('../app/services/http')
    localStorage.setItem(REFRESH_TOKEN_KEY, 'r1')
    const fetchMock = vi.fn().mockImplementation(async (url: string) =>
      url.endsWith('/auth/refresh') ? json({ access_token: 'a', refresh_token: 'r2' }) : json({ detail: 'still no' }, 401))
    vi.stubGlobal('fetch', fetchMock)

    await expect(apiFetch('/api/v1/orders')).rejects.toMatchObject({ status: 401 })
    expect(fetchMock).toHaveBeenCalledTimes(3) // request, refresh, one retry — then stop
  })

  it('never tries to refresh unauthenticated calls such as login', async () => {
    const { apiFetch } = await import('../app/services/http')
    localStorage.setItem(REFRESH_TOKEN_KEY, 'r1')
    const fetchMock = vi.fn().mockResolvedValue(json({ detail: 'Invalid email or password' }, 401))
    vi.stubGlobal('fetch', fetchMock)

    await expect(apiFetch('/api/v1/auth/login', { method: 'POST', auth: false })).rejects.toMatchObject({ status: 401 })
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
})
