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
    { path: '~/components/menu', pathPrefix: false },
    { path: '~/components/cart', pathPrefix: false },
    { path: '~/components/floor', pathPrefix: false },
  ],

  css: ['~/assets/css/main.css'],

  runtimeConfig: {
    // Server-only: used for SSR fetches inside Docker (e.g. http://backend:8000)
    apiUrl: process.env.NUXT_API_URL || process.env.NUXT_PUBLIC_API_URL || 'http://localhost:8000',
    public: {
      // Browser-facing API URL (e.g. http://localhost:8000)
      apiUrl: process.env.NUXT_PUBLIC_API_URL || 'http://localhost:8000',
    },
  },

  // Baseline security headers for every page (a full Content-Security-Policy comes later, once
  // per-tenant themes and third-party embeds are settled).
  routeRules: {
    '/**': {
      headers: {
        'X-Content-Type-Options': 'nosniff',
        'X-Frame-Options': 'DENY',
        'Referrer-Policy': 'strict-origin-when-cross-origin',
        'Permissions-Policy': 'camera=(), microphone=(), geolocation=()',
      },
    },
    // The booking widget is meant to be framed on a restaurant's own external site — everything
    // else stays DENY. CSP frame-ancestors (rather than X-Frame-Options, which can't allow "any
    // origin") is the mechanism for that; a future per-tenant allow-list can tighten this further.
    '/embed/**': {
      headers: {
        'X-Content-Type-Options': 'nosniff',
        'X-Frame-Options': '',
        'Content-Security-Policy': 'frame-ancestors *',
        'Referrer-Policy': 'strict-origin-when-cross-origin',
        'Permissions-Policy': 'camera=(), microphone=(), geolocation=()',
      },
    },
  },

  typescript: {
    strict: true,
    typeCheck: false,
  },
})
