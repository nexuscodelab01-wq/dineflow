// Every page belongs to one restaurant, worked out from the address. Load it first, and show a clear
// "nothing here" page (instead of a broken menu) when no restaurant lives at this address.
export default defineNuxtRouteMiddleware(async () => {
  const restaurant = useRestaurantStore()
  await restaurant.load()
  if (restaurant.notFound) {
    return showError(createError({
      statusCode: 404,
      statusMessage: 'No restaurant lives at this address',
      fatal: true,
    }))
  }
})
