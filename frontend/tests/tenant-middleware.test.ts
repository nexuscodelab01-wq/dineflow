import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// tenant.global.ts relies on Nuxt's auto-imports (defineNuxtRouteMiddleware, useRestaurantStore,
// showError, createError) rather than explicit imports — stub them as globals the same way Nuxt's
// build step would provide them, then dynamically import the middleware so it picks the stubs up.
// Regression test for a real bug: every dev/test environment always has DEFAULT_TENANT_SLUG set, so
// `restaurant.notFound` was never true there even on the bare platform domain — this middleware's
// unconditional 404 on "no restaurant" was never actually exercised until the first real deploy,
// where it silently made /login and /platform completely unreachable on the bare domain.

function stubRestaurant(notFound: boolean) {
  const load = vi.fn().mockResolvedValue(undefined)
  vi.stubGlobal('useRestaurantStore', () => ({ notFound, load }))
}

describe('tenant.global middleware', () => {
  let showError: ReturnType<typeof vi.fn>

  beforeEach(() => {
    vi.resetModules()
    showError = vi.fn()
    vi.stubGlobal('defineNuxtRouteMiddleware', (fn: unknown) => fn)
    vi.stubGlobal('showError', showError)
    vi.stubGlobal('createError', (opts: unknown) => opts)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  async function run(path: string, notFound: boolean) {
    stubRestaurant(notFound)
    const middleware = (await import('../app/middleware/tenant.global')).default
    return middleware({ path } as never, {} as never)
  }

  it('shows the 404 page when no restaurant resolves on an ordinary page', async () => {
    await run('/menu', true)
    expect(showError).toHaveBeenCalledWith(expect.objectContaining({ statusCode: 404 }))
  })

  it('never 404s when a restaurant resolves', async () => {
    await run('/menu', false)
    expect(showError).not.toHaveBeenCalled()
  })

  it.each(['/login', '/register', '/forgot-password', '/reset-password'])(
    'lets %s through even with no restaurant resolved (the platform admin login path)',
    async (path) => {
      await run(path, true)
      expect(showError).not.toHaveBeenCalled()
    },
  )

  it('lets every /platform route through with no restaurant resolved', async () => {
    await run('/platform/features', true)
    expect(showError).not.toHaveBeenCalled()
  })
})
