import { describe, expect, it } from 'vitest'
import { ALLERGENS, allergenLabel } from '../app/utils/allergens'

describe('allergens', () => {
  it('has 14 codes, matching the standard UK/EU allergen list backend/app/core/allergens.py declares', () => {
    expect(ALLERGENS).toHaveLength(14)
  })

  it('looks up a known code by its human label', () => {
    expect(allergenLabel('milk')).toBe('Milk')
    expect(allergenLabel('cereals_gluten')).toBe('Cereals containing gluten')
  })

  it('falls back to the raw code for anything unrecognised, rather than throwing', () => {
    expect(allergenLabel('not-a-real-code')).toBe('not-a-real-code')
  })
})
