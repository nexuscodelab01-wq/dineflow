import { describe, expect, it } from 'vitest'
import { anyFeatureOn, isFeatureOn, ORDERING_CHANNELS } from '../app/utils/features'

describe('feature helpers', () => {
  it('treats missing or not-yet-loaded flags as off', () => {
    expect(isFeatureOn(undefined, 'online_ordering')).toBe(false)
    expect(isFeatureOn({}, 'online_ordering')).toBe(false)
    expect(isFeatureOn({ online_ordering: true }, 'online_ordering')).toBe(true)
  })

  it('anyFeatureOn stays on while at least one flag in the list is on', () => {
    expect(anyFeatureOn({ pos: true }, ORDERING_CHANNELS)).toBe(true)
    expect(anyFeatureOn({ qr_table_ordering: true, pos: false }, ORDERING_CHANNELS)).toBe(true)
    expect(anyFeatureOn({ online_ordering: false, pos: false, qr_table_ordering: false }, ORDERING_CHANNELS)).toBe(false)
    expect(anyFeatureOn({}, ORDERING_CHANNELS)).toBe(false)
  })

  it('accepts a single key too', () => {
    expect(anyFeatureOn({ reservations: true }, 'reservations')).toBe(true)
    expect(anyFeatureOn({ reservations: false }, 'reservations')).toBe(false)
  })
})
