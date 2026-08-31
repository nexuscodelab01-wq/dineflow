import { defineStore } from 'pinia'
import type { LoginPayload, RegisterPayload, RoleName, User } from '~/types/auth'
import {
  clearStoredTokens,
  fetchCurrentUser,
  getStoredAccessToken,
  login as loginRequest,
  logoutRequest,
  register as registerRequest,
  storeTokens,
} from '~/services/auth'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: null as User | null,
    initialized: false,
    loading: false,
  }),

  getters: {
    isAuthenticated: state => Boolean(state.user && getStoredAccessToken()),
    role: state => state.user?.role.name ?? null,
    fullName: state =>
      state.user ? `${state.user.first_name} ${state.user.last_name}` : '',
    isAdmin: state =>
      ['RESTAURANT_ADMIN', 'SUPER_ADMIN'].includes(state.user?.role.name ?? ''),
    isStaff: state =>
      ['RESTAURANT_ADMIN', 'RESTAURANT_STAFF', 'SUPER_ADMIN'].includes(
        state.user?.role.name ?? '',
      ),
  },

  actions: {
    hasRole(...roles: RoleName[]) {
      const role = this.user?.role.name
      return role ? roles.includes(role) : false
    },

    async initialize() {
      if (this.initialized) return
      this.loading = true
      try {
        if (getStoredAccessToken()) {
          this.user = await fetchCurrentUser()
        }
      }
      catch {
        clearStoredTokens()
        this.user = null
      }
      finally {
        this.loading = false
        this.initialized = true
      }
    },

    async login(payload: LoginPayload) {
      this.loading = true
      try {
        const tokens = await loginRequest(payload)
        storeTokens(tokens)
        this.user = await fetchCurrentUser()
      }
      finally {
        this.loading = false
      }
    },

    async register(payload: RegisterPayload) {
      this.loading = true
      try {
        const tokens = await registerRequest(payload)
        storeTokens(tokens)
        this.user = await fetchCurrentUser()
      }
      finally {
        this.loading = false
      }
    },

    async logout() {
      try {
        await logoutRequest()
      }
      catch {
        // still clear local session
      }
      clearStoredTokens()
      this.user = null
    },
  },
})
