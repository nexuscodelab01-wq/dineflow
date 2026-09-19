/**
 * API client helpers — expanded in later phases.
 */
export function getApiBaseUrl(): string {
  const config = useRuntimeConfig()
  if (import.meta.server) {
    return (config.apiUrl as string) || (config.public.apiUrl as string)
  }
  return config.public.apiUrl as string
}

export async function fetchHealth(): Promise<{ status: string }> {
  const base = getApiBaseUrl()
  return await $fetch<{ status: string }>(`${base}/api/v1/health`)
}
