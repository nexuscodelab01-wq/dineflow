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

  describe('service charge', () => {
    const restaurant = {
      id: 1, name: 'Test', slug: 'test', tax_rate: '0.10', delivery_fee: '5.00', delivery_enabled: true, pickup_enabled: true,
      dine_in_enabled: true, is_active: true, service_charge_rate: '0.10', service_charge_order_types: ['DINE_IN'],
    }

    function cartWith24() {
      const cart = useCartStore()
      cart.lines = [{ id: '1', menu_item_id: 10, name: 'Burger', unit_price: 12, quantity: 2, modifier_option_ids: [], modifiers: [] }]
      return cart
    }

    it('adds the charge only for the chosen order types, untaxed by default', () => {
      const cart = cartWith24()
      expect(cart.computeTotals(restaurant, 'PICKUP').service_charge).toBe(0)
      const dineIn = cart.computeTotals(restaurant, 'DINE_IN')
      expect(dineIn.service_charge).toBe(2.4)
      expect(dineIn.tax).toBe(2.4)
      expect(dineIn.total).toBe(28.8)
    })

    it('puts the charge in the tax base when the restaurant taxes it', () => {
      const dineIn = cartWith24().computeTotals({ ...restaurant, service_charge_taxable: true }, 'DINE_IN')
      expect(dineIn.tax).toBe(2.64) // 10% of 26.40
      expect(dineIn.total).toBe(29.04)
    })
  })
})
