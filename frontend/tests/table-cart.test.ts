import { describe, expect, it } from 'vitest'
import { addLine, changeQuantity, lineCount, MAX_LINE_QUANTITY, subtotal, toRoundPayload } from '../app/utils/table-cart'

const burger = { menuItemId: 1, name: 'Burger', unitPrice: 12, quantity: 1, optionIds: [], optionNames: [] }

describe('table cart', () => {
  it('merges the same dish with the same options and note', () => {
    let lines = addLine([], burger)
    lines = addLine(lines, { ...burger, quantity: 2 })
    expect(lines).toHaveLength(1)
    expect(lines[0]!.quantity).toBe(3)
  })

  it('keeps different options or notes apart, whatever order the options came in', () => {
    let lines = addLine([], { ...burger, optionIds: [3, 2] })
    lines = addLine(lines, { ...burger, optionIds: [2, 3] })
    lines = addLine(lines, { ...burger, optionIds: [2] })
    lines = addLine(lines, { ...burger, instructions: 'No onions' })
    expect(lines.map(l => l.quantity)).toEqual([2, 1, 1])
  })

  it('caps a line and removes it at zero', () => {
    let lines = addLine([], { ...burger, quantity: 19 })
    lines = addLine(lines, { ...burger, quantity: 5 })
    expect(lines[0]!.quantity).toBe(MAX_LINE_QUANTITY)
    expect(changeQuantity(lines, lines[0]!.key, -MAX_LINE_QUANTITY)).toEqual([])
  })

  it('adds up in whole cents', () => {
    const lines = addLine(addLine([], { ...burger, unitPrice: 0.1, quantity: 3 }), { ...burger, menuItemId: 2, unitPrice: 0.2, quantity: 3 })
    expect(subtotal(lines)).toBe(0.9)
    expect(lineCount(lines)).toBe(6)
  })

  it('builds the request the API expects', () => {
    const lines = addLine([], { ...burger, quantity: 2, optionIds: [5], instructions: ' no ice ' })
    expect(toRoundPayload(lines, '  window seat ')).toEqual({
      items: [{ menu_item_id: 1, quantity: 2, modifier_option_ids: [5], special_instructions: 'no ice' }],
      notes: 'window seat',
    })
    expect(toRoundPayload(lines).notes).toBeNull()
  })
})
