import { defineStore } from 'pinia'
import type { Restaurant } from '~/types/menu'
import { fetchMyRestaurants } from '~/services/menu'

export const useAdminStore = defineStore('admin', {
  state: () => ({
    restaurant: null as Restaurant | null,
    restaurants: [] as Restaurant[],
    loading: false,
  }),

  getters: {
    restaurantId: state => state.restaurant?.id ?? null,
  },

  actions: {
    /** Pick the restaurant to manage: this site's own restaurant if the account may manage it, else the first. */
    async initialize() {
      if (this.restaurant) return this.restaurant
      if (import.meta.server) return null // the session token lives in the browser
      this.loading = true
      try {
        this.restaurants = await fetchMyRestaurants()
        const here = useRestaurantStore().id
        this.restaurant = this.restaurants.find(r => r.id === here) || this.restaurants[0] || null
        return this.restaurant
      }
      finally {
        this.loading = false
      }
    },

    reset() {
      this.restaurant = null
      this.restaurants = []
    },
  },
})
