<script setup lang="ts">
import { paletteCss } from '~/utils/palette'
import { resolveMediaUrl } from '~/utils/media'
import { getPublicApiBaseUrl } from '~/services/http'

// Rendered on the server, so a restaurant's colours, title, icon and social-share tags are there
// from the first paint — the same reasoning as the branding block below, just extended to SEO.
const branding = useBranding()
const restaurant = useRestaurantStore()
const url = useRequestURL()
// Captured here, in setup, not inside the lazy getters below — see useBranding.ts for why: on the
// server, resolving this lazily needs runWithContext, which wraps even a synchronous call in a
// Promise, and both useHead and useSeoMeta silently drop a value that turns out to be one.
const apiBase = getPublicApiBaseUrl()

const description = computed(() => {
  const current = restaurant.current
  return (current?.description || current?.about_text || 'Browse the menu, book a table, and order online.').slice(0, 300)
})
const shareImage = computed(() => {
  const gallery = restaurant.current?.gallery
  const fromGallery = gallery && gallery.length ? resolveMediaUrl(gallery[0], apiBase) : null
  return fromGallery || `${url.origin}/og-default.png`
})
const canonical = computed(() => `${url.origin}${url.pathname}`)

useHead(() => ({
  titleTemplate: (title?: string) => (branding.name.value ? (title ? `${title} · ${branding.name.value}` : branding.name.value) : (title ? `${title} · DineFlow` : 'DineFlow')),
  style: (branding.color.value || branding.secondaryColor.value) ? [{ key: 'brand-palette', innerHTML: paletteCss(branding.color.value, branding.secondaryColor.value) }] : [],
  link: branding.logo.value
    ? [{ key: 'brand-icon', rel: 'icon', href: branding.logo.value }, { key: 'canonical', rel: 'canonical', href: canonical.value }]
    : [
        // A restaurant with no custom branding still needs a real favicon — an absent one is a
        // browser-tab blank/broken-image icon, not a neutral default.
        { key: 'favicon-ico', rel: 'icon', href: '/favicon.ico', sizes: '32x32' },
        { key: 'favicon-svg-32', rel: 'icon', type: 'image/png', sizes: '32x32', href: '/favicon-32.png' },
        { key: 'apple-touch-icon', rel: 'apple-touch-icon', href: '/apple-touch-icon.png' },
        { key: 'canonical', rel: 'canonical', href: canonical.value },
      ],
}))

useSeoMeta({
  description,
  ogTitle: () => branding.name.value || restaurant.current?.name || 'DineFlow',
  ogDescription: description,
  ogType: 'website',
  ogUrl: canonical,
  ogImage: shareImage,
  twitterCard: 'summary_large_image',
  twitterTitle: () => branding.name.value || restaurant.current?.name || 'DineFlow',
  twitterDescription: description,
  twitterImage: shareImage,
})
</script>

<template>
  <NuxtLayout>
    <NuxtPage />
  </NuxtLayout>
  <AppToast />
  <ConfirmDialog />
</template>
