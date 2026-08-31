import { describe, expect, it } from 'vitest'
import { formatCurrency } from '../app/utils/format'

describe('formatCurrency', () => {
  it('formats USD amounts', () => {
    expect(formatCurrency(12.5)).toBe('$12.50')
  })
})
