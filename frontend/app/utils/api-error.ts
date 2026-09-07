export type ValidationErrorItem = {
  field: string
  message: string
}

export class ApiError extends Error {
  status: number
  errors?: ValidationErrorItem[]

  constructor(message: string, status: number, errors?: ValidationErrorItem[]) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.errors = errors
  }

  get isUnauthorized() {
    return this.status === 401
  }

  get isForbidden() {
    return this.status === 403
  }

  get isNotFound() {
    return this.status === 404
  }

  get isValidationError() {
    return this.status === 422
  }
}

export function parseApiErrorBody(body: unknown, status: number): ApiError {
  if (typeof body !== 'object' || body === null) {
    return new ApiError('Request failed', status)
  }

  const payload = body as { detail?: unknown, errors?: ValidationErrorItem[] }
  let message = 'Request failed'

  if (typeof payload.detail === 'string') {
    message = payload.detail
  }
  else if (Array.isArray(payload.detail)) {
    message = payload.detail.map((item) => {
      if (typeof item === 'object' && item !== null && 'msg' in item) {
        return String((item as { msg: unknown }).msg)
      }
      return String(item)
    }).join(', ')
  }

  if (status === 422 && payload.errors?.length) {
    const fieldMessages = payload.errors.map(e => `${e.field}: ${e.message}`).join('; ')
    message = fieldMessages || message
  }

  return new ApiError(message, status, payload.errors)
}
