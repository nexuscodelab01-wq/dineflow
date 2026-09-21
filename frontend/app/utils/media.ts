import { getApiBaseUrl } from '~/services/http'

/**
 * The small (≈400px) version of an uploaded photo. The API stores every optimised upload as
 * `<name>.webp` plus `<name>-thumb.webp`, so list pages can load the light one. Anything else
 * (older uploads, external links) has no thumbnail and is returned unchanged.
 */
export function thumbnailUrl(url?: string | null): string | null {
  if (!url) return null
  return /\/tenants\/\d+\/.+\.webp(\?.*)?$/.test(url) && !/-thumb\.webp/.test(url)
    ? url.replace(/\.webp(\?.*)?$/, '-thumb.webp$1')
    : url
}

/** Resolve menu/media URLs — relative `/uploads/...` paths need the API host. */
export function resolveMediaUrl(url?: string | null): string | null {
  if (!url) return null
  if (/^https?:\/\//i.test(url) || url.startsWith('data:')) return url
  const base = getApiBaseUrl().replace(/\/$/, '')
  return url.startsWith('/') ? `${base}${url}` : `${base}/${url}`
}
