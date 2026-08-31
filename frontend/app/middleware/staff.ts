export default defineNuxtRouteMiddleware(async () => {
  const auth = useAuthStore()
  if (!auth.initialized) await auth.initialize()

  if (!auth.isAuthenticated) {
    return navigateTo('/login?redirect=/admin')
  }

  if (!auth.isStaff) {
    return navigateTo('/')
  }
})
