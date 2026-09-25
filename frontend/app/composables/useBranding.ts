import { resolveMediaUrl } from '~/utils/media'
import { getPublicApiBaseUrl } from '~/services/http'

/** The restaurant's own look on its site: name, logo and colour, once `custom_branding` is switched on. */
export function useBranding() {
  const restaurant = useRestaurantStore()
  const enabled = useFeature('custom_branding')
  // Captured now, while we're safely inside setup — the head manager reads `logo.value` later, outside
  // it, and resolveMediaUrl would otherwise need to call useRuntimeConfig() at that point itself. On
  // the server that used to go through nuxtApp.runWithContext(), which wraps even a synchronous
  // callback in a Promise there — so `logo.value` was a Promise object, not a string, until client-side
  // hydration silently overwrote it. Passing the base in avoids needing runWithContext at all.
  const apiBase = getPublicApiBaseUrl()
  return {
    enabled,
    name: computed(() => (enabled.value ? restaurant.current?.name ?? null : null)),
    logo: computed(() => (enabled.value ? resolveMediaUrl(restaurant.current?.logo_url, apiBase) : null)),
    color: computed(() => (enabled.value ? restaurant.current?.primary_color ?? null : null)),
    /** Accent colour for badges/highlights; falls back to the default amber when the restaurant hasn't set one. */
    secondaryColor: computed(() => (enabled.value ? restaurant.current?.secondary_color ?? null : null)),
  }
}
