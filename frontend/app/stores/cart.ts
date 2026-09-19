import { defineStore } from 'pinia'
import type { CartLine, CartLineModifier, CartTotals } from '~/types/cart'
import type { MenuItemDetail } from '~/types/menu'
import type { Restaurant } from '~/types/menu'

const CART_KEY = 'dineflow_cart'

function loadLines(): CartLine[] {
  if (import.meta.server) return []
  try {
    const raw = localStorage.getItem(CART_KEY)
    return raw ? JSON.parse(raw) as CartLine[] : []
  }
  catch {
    return []
  }
}

function saveLines(lines: CartLine[]) {
  if (import.meta.server) return
  localStorage.setItem(CART_KEY, JSON.stringify(lines))
}

function lineKey(menuItemId: number, modifierOptionIds: number[], instructions?: string) {
  const mods = [...modifierOptionIds].sort((a, b) => a - b).join(',')
  return `${menuItemId}:${mods}:${instructions || ''}`
}

export const useCartStore = defineStore('cart', {
  state: () => ({
    restaurantId: null as number | null,
    lines: loadLines(),
  }),

  getters: {
    itemCount: state => state.lines.reduce((sum, line) => sum + line.quantity, 0),
    isEmpty: state => state.lines.length === 0,
    subtotal: state => state.lines.reduce((sum, line) => sum + line.unit_price * line.quantity, 0),
  },

  actions: {
    persist() {
      saveLines(this.lines)
    },

    clear() {
      this.lines = []
      this.restaurantId = null
      this.persist()
    },

    setRestaurant(restaurantId: number) {
      if (this.restaurantId && this.restaurantId !== restaurantId && this.lines.length) {
        this.lines = []
      }
      this.restaurantId = restaurantId
      this.persist()
    },

    addItem(
      item: MenuItemDetail,
      selectedOptionIds: number[],
      quantity = 1,
      specialInstructions?: string,
    ) {
      this.setRestaurant(item.restaurant_id)

      const modifiers: CartLineModifier[] = []
      let adjustment = 0
      for (const modifier of item.modifiers) {
        for (const option of modifier.options) {
          if (selectedOptionIds.includes(option.id)) {
            const price = Number(option.price_adjustment)
            adjustment += price
            modifiers.push({
              option_id: option.id,
              modifier_name: modifier.name,
              option_name: option.name,
              price_adjustment: price,
            })
          }
        }
      }

      const unitPrice = Number(item.price) + adjustment
      const key = lineKey(item.id, selectedOptionIds, specialInstructions)
      const existing = this.lines.find(
        l => lineKey(l.menu_item_id, l.modifier_option_ids, l.special_instructions) === key,
      )

      if (existing) {
        existing.quantity += quantity
      }
      else {
        this.lines.push({
          id: crypto.randomUUID(),
          menu_item_id: item.id,
          name: item.name,
          image_url: item.image_url,
          unit_price: unitPrice,
          quantity,
          modifier_option_ids: selectedOptionIds,
          modifiers,
          special_instructions: specialInstructions,
        })
      }
      this.persist()
    },

    updateQuantity(lineId: string, quantity: number) {
      const line = this.lines.find(l => l.id === lineId)
      if (!line) return
      if (quantity <= 0) {
        this.removeLine(lineId)
        return
      }
      line.quantity = quantity
      this.persist()
    },

    removeLine(lineId: string) {
      this.lines = this.lines.filter(l => l.id !== lineId)
      if (!this.lines.length) this.restaurantId = null
      this.persist()
    },

    computeTotals(restaurant: Restaurant, orderType: 'DELIVERY' | 'PICKUP' | 'DINE_IN', discount = 0): CartTotals {
      const subtotal = this.lines.reduce((sum, line) => sum + line.unit_price * line.quantity, 0)
      const taxable = Math.max(subtotal - discount, 0)
      const taxRate = Number(restaurant.tax_rate)
      const tax = Math.round(taxable * taxRate * 100) / 100
      const deliveryFee = orderType === 'DELIVERY' ? Number(restaurant.delivery_fee) : 0
      const total = Math.round((taxable + tax + deliveryFee) * 100) / 100
      return { subtotal, tax, delivery_fee: deliveryFee, discount, total }
    },

    toOrderItems() {
      return this.lines.map(line => ({
        menu_item_id: line.menu_item_id,
        quantity: line.quantity,
        modifier_option_ids: line.modifier_option_ids,
        special_instructions: line.special_instructions,
      }))
    },
  },
})
