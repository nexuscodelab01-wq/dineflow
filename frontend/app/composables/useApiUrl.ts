export function useApiUrl() {
  const config = useRuntimeConfig()
  return computed(() => {
    if (import.meta.server) {
      return (config.apiUrl as string) || (config.public.apiUrl as string)
    }
    return config.public.apiUrl as string
  })
}
