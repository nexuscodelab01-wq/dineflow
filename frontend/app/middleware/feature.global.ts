import { anyFeatureOn } from '~/utils/features'

// A page that belongs to a feature flag (`definePageMeta({ feature: 'reservations' })`) simply doesn't exist while that
// flag is off for the restaurant: a 404 for the public site, back to the dashboard for the admin. The API refuses the
// same calls on its own, so this is about not offering — or leaving reachable by URL — something that is switched off.
export default defineNuxtRouteMiddleware(async (to) => {
  const feature = to.meta.feature
  if (!feature) return

  const site = useRestaurantStore()
  await site.load()
  if (!site.current) return // no restaurant at this address: tenant.global.ts deals with that

  if (to.path.startsWith('/admin')) {
    const admin = useAdminStore()
    // A platform admin managing some other restaurant: this site's flags say nothing about it (the nav does the same).
    if (admin.restaurantId && admin.restaurantId !== site.current.id) return
    if (!anyFeatureOn(site.current.features, feature)) return navigateTo('/admin')
    return
  }

  if (!anyFeatureOn(site.current.features, feature)) {
    return showError(createError({ statusCode: 404, statusMessage: 'This page isn\'t available', fatal: true }))
  }
})
