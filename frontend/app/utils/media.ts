import { getApiBaseUrl } from '~/services/http'

/** Resolve menu/media URLs — relative `/uploads/...` paths need the API host. */
export function resolveMediaUrl(url?: string | null): string | null {
  if (!url) return null
  if (/^https?:\/\//i.test(url) || url.startsWith('data:')) return url
  const base = getApiBaseUrl().replace(/\/$/, '')
  return url.startsWith('/') ? `${base}${url}` : `${base}/${url}`
}
