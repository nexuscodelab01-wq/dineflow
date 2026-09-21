import { resolveMediaUrl } from '~/utils/media'

/** The restaurant's own look on its site: name, logo and colour, once `custom_branding` is switched on. */
export function useBranding() {
  const restaurant = useRestaurantStore()
  const enabled = useFeature('custom_branding')
  const nuxtApp = useNuxtApp() // the head manager reads these outside a component, so re-enter the Nuxt context
  return {
    enabled,
    name: computed(() => (enabled.value ? restaurant.current?.name ?? null : null)),
    logo: computed(() => (enabled.value ? nuxtApp.runWithContext(() => resolveMediaUrl(restaurant.current?.logo_url)) : null)),
    color: computed(() => (enabled.value ? restaurant.current?.primary_color ?? null : null)),
  }
}
