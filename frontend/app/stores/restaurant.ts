import { defineStore } from 'pinia'
import type { Restaurant } from '~/types/menu'
import { fetchRestaurant } from '~/services/menu'

export const useRestaurantStore = defineStore('restaurant', {
  state: () => ({
    current: null as Restaurant | null,
    loading: false,
  }),

  actions: {
    async load(slug?: string) {
      const config = useRuntimeConfig()
      const target = slug || (config.public.defaultRestaurantSlug as string) || 'bella-vista-kitchen'
      if (this.current?.slug === target) return this.current

      this.loading = true
      try {
        this.current = await fetchRestaurant(target)
        return this.current
      }
      finally {
        this.loading = false
      }
    },
  },
})
