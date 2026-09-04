import { defineStore } from 'pinia'
import type { Restaurant } from '~/types/menu'
import { fetchRestaurants } from '~/services/menu'

export const useAdminStore = defineStore('admin', {
  state: () => ({
    restaurant: null as Restaurant | null,
    loading: false,
  }),

  getters: {
    restaurantId: state => state.restaurant?.id ?? null,
  },

  actions: {
    async initialize() {
      if (this.restaurant) return this.restaurant
      this.loading = true
      try {
        const config = useRuntimeConfig()
        const slug = config.public.defaultRestaurantSlug as string
        const restaurants = await fetchRestaurants()
        this.restaurant = restaurants.find(r => r.slug === slug) || restaurants[0] || null
        return this.restaurant
      }
      finally {
        this.loading = false
      }
    },
  },
})
