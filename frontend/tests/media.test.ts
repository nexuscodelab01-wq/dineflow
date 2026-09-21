import { describe, expect, it } from 'vitest'
import { thumbnailUrl } from '../app/utils/media'

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
