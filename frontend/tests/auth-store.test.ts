import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAuthStore } from '../app/stores/auth'

vi.mock('../app/services/auth', () => ({
  getStoredAccessToken: vi.fn(() => null),
  clearStoredTokens: vi.fn(),
  fetchCurrentUser: vi.fn(),
  login: vi.fn(),
  register: vi.fn(),
  logoutRequest: vi.fn(),
  storeTokens: vi.fn(),
}))

describe('useAuthStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('starts unauthenticated', () => {
    const store = useAuthStore()
    expect(store.isAuthenticated).toBe(false)
    expect(store.user).toBeNull()
  })

  it('detects admin roles', () => {
    const store = useAuthStore()
    store.user = {
      id: 1,
      email: 'admin@demo.com',
      first_name: 'Admin',
      last_name: 'User',
      is_active: true,
      role: { id: 1, name: 'RESTAURANT_ADMIN' },
    }
    expect(store.isAdmin).toBe(true)
    expect(store.hasRole('RESTAURANT_ADMIN')).toBe(true)
  })
})
