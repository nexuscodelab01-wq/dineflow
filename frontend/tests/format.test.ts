import { describe, expect, it } from 'vitest'
import { formatCurrency } from '../app/utils/format'

describe('formatCurrency', () => {
  it('formats USD amounts', () => {
    expect(formatCurrency(12.5)).toBe('$12.50')
  })

  it('formats Canadian dollars without the CA prefix under en-CA', () => {
    expect(formatCurrency(12.5, 'CAD', 'en-CA')).toBe('$12.50')
    expect(formatCurrency(12.5, 'CAD')).toBe('CA$12.50')
  })
})
