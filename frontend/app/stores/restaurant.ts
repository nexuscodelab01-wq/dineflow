import { defineStore } from 'pinia'
import type { Restaurant } from '~/types/menu'
import { fetchTenant } from '~/services/menu'
import { ApiError } from '~/services/http'

/** The restaurant this site belongs to, worked out from the address in the browser (never hard-coded). */
export const useRestaurantStore = defineStore('restaurant', {
  state: () => ({
    current: null as Restaurant | null,
    /** True once we asked and no restaurant lives at this address. */
    notFound: false,
    loading: false,
  }),

  getters: {
    id: state => state.current?.id ?? null,
  },

  actions: {
    async load() {
      if (this.current) return this.current
      this.loading = true
      try {
        this.current = await fetchTenant(useRequestURL().host)
        this.notFound = false
        return this.current
      }
      catch (err) {
        if (err instanceof ApiError && err.status === 404) {
          this.notFound = true
          return null
        }
        throw err
      }
      finally {
        this.loading = false
      }
    },
  },
})
