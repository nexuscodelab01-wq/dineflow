export default defineNuxtRouteMiddleware(async (to) => {
  // The session token lives in localStorage, which the server can't see — decide on the client.
  if (import.meta.server) return
  const auth = useAuthStore()
  if (!auth.initialized) await auth.initialize()

  if (!auth.isAuthenticated) {
    return navigateTo({
      path: '/login',
      query: { redirect: to.fullPath },
    })
  }
})
