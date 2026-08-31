export function useApiUrl() {
  const config = useRuntimeConfig()
  return computed(() => config.public.apiUrl as string)
}
