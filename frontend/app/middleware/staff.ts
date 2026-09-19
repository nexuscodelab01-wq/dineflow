export default defineNuxtRouteMiddleware(async () => {
  // The session token lives in localStorage, which the server can't see — decide on the client.
  if (import.meta.server) return
  const auth = useAuthStore()
  if (!auth.initialized) await auth.initialize()

  if (!auth.isAuthenticated) {
    return navigateTo('/login?redirect=/admin')
  }

  if (!auth.isStaff) {
    return navigateTo('/')
  }
})
