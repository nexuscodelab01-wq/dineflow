import { afterEach, describe, expect, it, vi } from 'vitest'
import { resolveMediaUrl, thumbnailUrl } from '../app/utils/media'

describe('thumbnailUrl', () => {
  it('points optimised uploads at their small version', () => {
    expect(thumbnailUrl('/uploads/tenants/1/menu/abc123.webp')).toBe('/uploads/tenants/1/menu/abc123-thumb.webp')
    expect(thumbnailUrl('https://cdn.example.com/tenants/42/menu/x.webp')).toBe('https://cdn.example.com/tenants/42/menu/x-thumb.webp')
    expect(thumbnailUrl('https://cdn.example.com/tenants/42/menu/x.webp?v=2')).toBe('https://cdn.example.com/tenants/42/menu/x-thumb.webp?v=2')
  })

  it('leaves everything without a known thumbnail untouched', () => {
    expect(thumbnailUrl('/uploads/menu/r1-old.png')).toBe('/uploads/menu/r1-old.png')                      // legacy upload
    expect(thumbnailUrl('https://images.unsplash.com/photo-1.webp')).toBe('https://images.unsplash.com/photo-1.webp')   // external
    expect(thumbnailUrl('/uploads/tenants/1/menu/abc-thumb.webp')).toBe('/uploads/tenants/1/menu/abc-thumb.webp')       // already a thumb
    expect(thumbnailUrl('/uploads/tenants/1/branding/logo.png')).toBe('/uploads/tenants/1/branding/logo.png')
  })

  it('handles missing values', () => {
    expect(thumbnailUrl(null)).toBeNull()
    expect(thumbnailUrl(undefined)).toBeNull()
    expect(thumbnailUrl('')).toBeNull()
  })
})

describe('resolveMediaUrl', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('leaves an absolute or data URL untouched', () => {
    expect(resolveMediaUrl('https://cdn.example.com/x.webp')).toBe('https://cdn.example.com/x.webp')
    expect(resolveMediaUrl('http://cdn.example.com/x.webp')).toBe('http://cdn.example.com/x.webp')
    expect(resolveMediaUrl('data:image/png;base64,abc')).toBe('data:image/png;base64,abc')
  })

  it('handles missing values without touching the config', () => {
    expect(resolveMediaUrl(null)).toBeNull()
    expect(resolveMediaUrl(undefined)).toBeNull()
    expect(resolveMediaUrl('')).toBeNull()
  })

  it('joins a relative upload path onto an explicitly passed base, ignoring the config entirely', () => {
    // No useRuntimeConfig stub at all — proves the explicit `base` path never calls a composable,
    // which is the whole point of accepting one (see the function's own docstring).
    expect(resolveMediaUrl('/uploads/tenants/1/menu/x.webp', 'https://passed-in.example.com')).toBe(
      'https://passed-in.example.com/uploads/tenants/1/menu/x.webp',
    )
    expect(resolveMediaUrl('/uploads/x.webp', 'https://passed-in.example.com/')).toBe('https://passed-in.example.com/uploads/x.webp')
  })

  it('without an explicit base, always resolves against the *public* API URL — never an internal-only one', () => {
    // The classic Docker split: the Nuxt server can reach the backend at an internal hostname, but a
    // URL embedded in rendered markup has to be one the *browser* (or a crawler) can also reach.
    vi.stubGlobal('useRuntimeConfig', () => ({
      apiUrl: 'http://backend:8000', // server-only; must never leak into a resolved media URL
      public: { apiUrl: 'http://localhost:8000' },
    }))
    expect(resolveMediaUrl('/uploads/tenants/1/menu/x.webp')).toBe('http://localhost:8000/uploads/tenants/1/menu/x.webp')
  })
})
