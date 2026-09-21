import { defineConfig } from 'vitest/config'
import { resolve } from 'node:path'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [
    vue(),
    {
      // Nuxt substitutes these flags at build time; tests run as if in the browser.
      name: 'nuxt-import-meta-flags',
      enforce: 'pre',
      transform(code, id) {
        if (!id.includes('/app/') || id.includes('node_modules')) return null
        return code.replace(/import\.meta\.client/g, 'true').replace(/import\.meta\.server/g, 'false')
      },
    },
  ],
  resolve: {
    alias: {
      '~': resolve(__dirname, './app'),
      '@': resolve(__dirname, './app'),
    },
  },
  test: {
    environment: 'happy-dom',
    include: ['tests/**/*.{test,spec}.{js,ts}'],
  },
})
