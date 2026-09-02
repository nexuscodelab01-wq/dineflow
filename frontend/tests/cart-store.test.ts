import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useCartStore } from '../app/stores/cart'

describe('useCartStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  it('adds items and computes subtotal', () => {
    const cart = useCartStore()
    cart.lines = [{
      id: '1',
      menu_item_id: 10,
      name: 'Burger',
      unit_price: 12,
      quantity: 2,
      modifier_option_ids: [],
      modifiers: [],
    }]
    cart.restaurantId = 1

    const totals = cart.computeTotals({
      id: 1,
      name: 'Test',
      slug: 'test',
      tax_rate: '0.10',
      delivery_fee: '5.00',
      delivery_enabled: true,
      pickup_enabled: true,
      dine_in_enabled: true,
      is_active: true,
    }, 'PICKUP')

    expect(totals.subtotal).toBe(24)
    expect(totals.tax).toBe(2.4)
    expect(totals.total).toBe(26.4)
  })
})
