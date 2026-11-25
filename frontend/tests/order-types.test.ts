import { describe, expect, it } from 'vitest'
import { availableOrderTypes } from '../app/utils/orderTypes'

const on = { pickup_enabled: true, delivery_enabled: true, dine_in_enabled: true }

describe('availableOrderTypes', () => {
  it('offers everything that is on', () => {
    expect(availableOrderTypes(on, true)).toEqual(['PICKUP', 'DELIVERY', 'DINE_IN'])
  })
  it('hides delivery for a pickup-only restaurant', () => {
    expect(availableOrderTypes({ ...on, delivery_enabled: false }, false)).toEqual(['PICKUP'])
  })
  it('hides pickup for a delivery-only restaurant', () => {
    expect(availableOrderTypes({ ...on, pickup_enabled: false }, false)).toEqual(['DELIVERY'])
  })
  it('needs reservations on for dine-in', () => {
    expect(availableOrderTypes(on, false)).toEqual(['PICKUP', 'DELIVERY'])
  })
  it('can be empty', () => {
    expect(availableOrderTypes({ pickup_enabled: false, delivery_enabled: false, dine_in_enabled: false }, true)).toEqual([])
  })
})
