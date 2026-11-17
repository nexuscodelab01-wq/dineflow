import { describe, expect, it } from 'vitest'
import { allergenText, dishTypeText } from '../app/utils/menuLabels'
import type { MenuLabel } from '../app/types/menu'

const label = (code: string, text: string, kind: MenuLabel['kind'] = 'allergen'): MenuLabel =>
  ({ id: 1, kind, code, label: text, sort_order: 0 })

describe('menu label text', () => {
  it("uses the restaurant's own name for a code, including one it renamed", () => {
    expect(allergenText([label('milk', 'Dairy')], 'milk')).toBe('Dairy')
    expect(dishTypeText([label('vegan', 'Vegan', 'dish_type')], 'vegan')).toBe('Vegan')
  })

  it('falls back to the standard allergen name before the list has loaded', () => {
    expect(allergenText([], 'cereals_gluten')).toBe('Cereals containing gluten')
  })

  it('shows a readable form of a code the restaurant has deleted, never a blank', () => {
    expect(allergenText([], 'kiwi_fruit')).toBe('Kiwi fruit')
    expect(dishTypeText([], 'gluten_free')).toBe('Gluten free')
  })
})
