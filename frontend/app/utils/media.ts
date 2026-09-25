import { getPublicApiBaseUrl } from '~/services/http'

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

/**
 * Resolve menu/media URLs — relative `/uploads/...` paths need the API host.
 *
 * Always the *public* API address (`getPublicApiBaseUrl`), never the Nuxt server's own internal one:
 * this URL goes into an `<img src>`/`<link href>`/JSON-LD field the browser fetches itself, not a
 * request the Nuxt server makes. Using the internal address here (as this once did, unconditionally
 * calling the same base as `apiFetch`) rendered image URLs like `http://backend:8000/...` into the
 * page's initial HTML in Docker — unreachable by any real browser, and silently papered over the
 * moment client-side hydration repainted it with the right URL. Broken for anything that reads the
 * page without running its JS: a crawler, a share-link preview bot, `curl`, view-source.
 *
 * `base` lets a caller pass an already-resolved URL instead of having this call a composable itself —
 * needed when this runs lazily from outside a component's setup (e.g. inside `useHead`'s callback,
 * which Nuxt's head manager evaluates later and outside the Nuxt context, where calling a composable
 * would throw, or — wrapped in `runWithContext` on the server — silently return a Promise instead of a
 * string: see useBranding.ts).
 */
export function resolveMediaUrl(url?: string | null, base?: string): string | null {
  if (!url) return null
  if (/^https?:\/\//i.test(url) || url.startsWith('data:')) return url
  const apiBase = (base ?? getPublicApiBaseUrl()).replace(/\/$/, '')
  return url.startsWith('/') ? `${apiBase}${url}` : `${apiBase}/${url}`
}
