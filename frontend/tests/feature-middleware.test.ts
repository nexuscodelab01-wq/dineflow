import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// feature.global.ts: a page tagged with `definePageMeta({ feature })` doesn't exist while the flag is off.

describe('feature.global middleware', () => {
  let showError: ReturnType<typeof vi.fn>
  let navigateTo: ReturnType<typeof vi.fn>

  beforeEach(() => {
    vi.resetModules()
    showError = vi.fn()
    navigateTo = vi.fn((to: string) => `redirect:${to}`)
    vi.stubGlobal('defineNuxtRouteMiddleware', (fn: unknown) => fn)
    vi.stubGlobal('showError', showError)
    vi.stubGlobal('createError', (opts: unknown) => opts)
    vi.stubGlobal('navigateTo', navigateTo)
  })

  afterEach(() => vi.unstubAllGlobals())

  async function run(path: string, feature: string | undefined, opts: { features?: Record<string, boolean>, noRestaurant?: boolean, managing?: number | null } = {}) {
    const load = vi.fn().mockResolvedValue(undefined)
    vi.stubGlobal('useRestaurantStore', () => ({ load, current: opts.noRestaurant ? null : { id: 1, features: opts.features ?? {} } }))
    vi.stubGlobal('useAdminStore', () => ({ restaurantId: opts.managing ?? null }))
    const middleware = (await import('../app/middleware/feature.global')).default
    return middleware({ path, meta: { feature } } as never, {} as never)
  }

  it('ignores pages that belong to no feature', async () => {
    await run('/menu', undefined)
    expect(showError).not.toHaveBeenCalled()
    expect(navigateTo).not.toHaveBeenCalled()
  })

  it('lets a page through while its flag is on', async () => {
    await run('/reserve', 'reservations', { features: { reservations: true } })
    expect(showError).not.toHaveBeenCalled()
  })

  it('404s a public page whose flag is off — booking is not reachable by URL', async () => {
    await run('/reserve', 'reservations', { features: { reservations: false } })
    expect(showError).toHaveBeenCalledWith(expect.objectContaining({ statusCode: 404 }))
  })

  it('treats a flag that is missing as off', async () => {
    await run('/reviews', 'reviews', { features: {} })
    expect(showError).toHaveBeenCalled()
  })

  it('sends an admin page whose flag is off back to the dashboard', async () => {
    const result = await run('/admin/waitlist', 'reservations', { features: { reservations: false } })
    expect(navigateTo).toHaveBeenCalledWith('/admin')
    expect(result).toBe('redirect:/admin')
  })

  it('leaves a platform admin managing another restaurant alone', async () => {
    await run('/admin/waitlist', 'reservations', { features: { reservations: false }, managing: 99 })
    expect(navigateTo).not.toHaveBeenCalled()
  })

  it('does nothing when no restaurant resolved — the tenant middleware owns that case', async () => {
    await run('/reserve', 'reservations', { noRestaurant: true })
    expect(showError).not.toHaveBeenCalled()
  })
})
