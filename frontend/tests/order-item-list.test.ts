import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import OrderItemList from '../app/components/orders/OrderItemList.vue'
import type { OrderItem } from '../app/types/order'

const item = (over: Partial<OrderItem> = {}): OrderItem => ({
  id: 1, menu_item_id: 10, item_name: 'Margherita Pizza', quantity: 2, unit_price: '18.00', line_total: '36.00',
  special_instructions: null, modifiers: [], ...over,
})

describe('OrderItemList', () => {
  it('shows quantity and name', () => {
    const w = mount(OrderItemList, { props: { items: [item()] } })
    expect(w.text()).toContain('2×')
    expect(w.text()).toContain('Margherita Pizza')
    expect(w.find('[data-testid="special-instructions"]').exists()).toBe(false)
  })

  it('shows special instructions prominently (the kitchen bug)', () => {
    const w = mount(OrderItemList, { props: { items: [item({ special_instructions: 'No onions, extra crispy' })], variant: 'kitchen' } })
    const note = w.find('[data-testid="special-instructions"]')
    expect(note.exists()).toBe(true)
    expect(note.text()).toContain('No onions, extra crispy')
    expect(note.classes().join(' ')).toContain('bg-amber-100')
  })

  it('lists chosen options — as "+ Large" for the kitchen, "Size: Large" for guests', () => {
    const modifiers = [{ id: 1, modifier_name: 'Size', option_name: 'Large', price_adjustment: '2.00' }]
    expect(mount(OrderItemList, { props: { items: [item({ modifiers })], variant: 'kitchen' } }).text()).toContain('+ Large')
    expect(mount(OrderItemList, { props: { items: [item({ modifiers })] } }).text()).toContain('Size: Large')
  })

  it('only shows prices when asked', () => {
    expect(mount(OrderItemList, { props: { items: [item()] } }).text()).not.toContain('$36.00')
    expect(mount(OrderItemList, { props: { items: [item()], showPrices: true } }).text()).toContain('$36.00')
  })

  it('renders instructions as text, never as HTML', () => {
    const w = mount(OrderItemList, { props: { items: [item({ special_instructions: '<img src=x onerror=alert(1)>' })] } })
    expect(w.find('img').exists()).toBe(false)
    expect(w.text()).toContain('<img src=x onerror=alert(1)>')
  })
})
