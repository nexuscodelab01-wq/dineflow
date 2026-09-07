import { describe, expect, it } from 'vitest'
import { ApiError, parseApiErrorBody } from '../app/utils/api-error'

describe('parseApiErrorBody', () => {
  it('parses string detail messages', () => {
    const error = parseApiErrorBody({ detail: 'Invalid credentials' }, 401)
    expect(error).toBeInstanceOf(ApiError)
    expect(error.message).toBe('Invalid credentials')
    expect(error.status).toBe(401)
    expect(error.isUnauthorized).toBe(true)
  })

  it('parses validation errors with field messages', () => {
    const error = parseApiErrorBody(
      {
        detail: 'Validation failed',
        errors: [
          { field: 'email', message: 'Invalid email address' },
          { field: 'password', message: 'Password too short' },
        ],
      },
      422,
    )
    expect(error.isValidationError).toBe(true)
    expect(error.message).toContain('email: Invalid email address')
    expect(error.errors).toHaveLength(2)
  })

  it('falls back for unknown payloads', () => {
    const error = parseApiErrorBody(null, 500)
    expect(error.message).toBe('Request failed')
    expect(error.status).toBe(500)
  })
})
