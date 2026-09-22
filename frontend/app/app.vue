<script setup lang="ts">
import { paletteCss } from '~/utils/palette'

// Rendered on the server, so a restaurant's colours, title and icon are there from the first paint.
const branding = useBranding()
useHead(() => ({
  titleTemplate: (title?: string) => (branding.name.value ? (title ? `${title} · ${branding.name.value}` : branding.name.value) : (title ? `${title} · DineFlow` : 'DineFlow')),
  style: (branding.color.value || branding.secondaryColor.value) ? [{ key: 'brand-palette', innerHTML: paletteCss(branding.color.value, branding.secondaryColor.value) }] : [],
  link: branding.logo.value ? [{ key: 'brand-icon', rel: 'icon', href: branding.logo.value }] : [],
}))
</script>

<template>
  <NuxtLayout>
    <NuxtPage />
  </NuxtLayout>
  <AppToast />
  <ConfirmDialog />
</template>
