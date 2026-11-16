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

describe('CUSTOMER_ACCOUNT_FEATURES', () => {
  it('lists exactly the features a customer account is for', async () => {
    const { CUSTOMER_ACCOUNT_FEATURES } = await import('../app/utils/features')
    expect([...CUSTOMER_ACCOUNT_FEATURES].sort()).toEqual(['loyalty', 'online_ordering', 'reservations', 'reviews'])
  })

  it('a menu-only site (all four off) has no use for customer accounts', async () => {
    const { anyFeatureOn, CUSTOMER_ACCOUNT_FEATURES } = await import('../app/utils/features')
    expect(anyFeatureOn({ online_ordering: false, reservations: false, loyalty: false, reviews: false }, CUSTOMER_ACCOUNT_FEATURES)).toBe(false)
    expect(anyFeatureOn({ online_ordering: false, reviews: true }, CUSTOMER_ACCOUNT_FEATURES)).toBe(true)
  })
})
