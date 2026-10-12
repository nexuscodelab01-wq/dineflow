// Every page belongs to one restaurant, worked out from the address — except the handful that are
// platform-wide (the platform console, and the shared auth pages it sends people through, e.g.
// /platform redirecting an unauthenticated admin to /login). Those already handle an absent
// restaurant themselves (login.vue etc. pass `restaurant.id` as optional). Never actually exercised
// until the first real deploy off a real domain — every dev/test environment always has
// DEFAULT_TENANT_SLUG set, so `restaurant.notFound` was never true there even on the bare domain.
const TENANT_OPTIONAL = new Set(['/login', '/register', '/forgot-password', '/reset-password'])

export default defineNuxtRouteMiddleware(async (to) => {
  const restaurant = useRestaurantStore()
  await restaurant.load()
  if (restaurant.notFound && !TENANT_OPTIONAL.has(to.path) && !to.path.startsWith('/platform')) {
    return showError(createError({
      statusCode: 404,
      statusMessage: 'No restaurant lives at this address',
      fatal: true,
    }))
  }
})
