// https://nuxt.com/docs/api/configuration/nuxt-config
export default defineNuxtConfig({
  compatibilityDate: '2025-07-15',
  future: {
    compatibilityVersion: 4,
  },
  devtools: { enabled: true },

  modules: [
    '@nuxtjs/tailwindcss',
    '@pinia/nuxt',
  ],

  components: [
    { path: '~/components/ui', pathPrefix: false },
    { path: '~/components/orders', pathPrefix: false },
    { path: '~/components/admin', pathPrefix: false },
  ],

  css: ['~/assets/css/main.css'],

  runtimeConfig: {
    // Server-only: used for SSR fetches inside Docker (e.g. http://backend:8000)
    apiUrl: process.env.NUXT_API_URL || process.env.NUXT_PUBLIC_API_URL || 'http://localhost:8000',
    public: {
      // Browser-facing API URL (e.g. http://localhost:8000)
      apiUrl: process.env.NUXT_PUBLIC_API_URL || 'http://localhost:8000',
      defaultRestaurantSlug: process.env.NUXT_PUBLIC_DEFAULT_RESTAURANT_SLUG || 'bella-vista-kitchen',
    },
  },

  typescript: {
    strict: true,
    typeCheck: false,
  },
})
