import { describe, expect, it } from 'vitest'
import { isFeatureOn } from '../app/utils/features'

describe('isFeatureOn', () => {
  it('is on only when the flag is explicitly true', () => {
    expect(isFeatureOn({ reservations: true }, 'reservations')).toBe(true)
    expect(isFeatureOn({ reservations: false }, 'reservations')).toBe(false)
  })

  it('treats unknown flags and a missing flag list as off', () => {
    expect(isFeatureOn({}, 'kitchen_v2')).toBe(false)
    expect(isFeatureOn(undefined, 'kitchen_v2')).toBe(false)
    expect(isFeatureOn(null, 'kitchen_v2')).toBe(false)
  })
})
