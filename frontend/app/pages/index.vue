<template>
  <section class="relative overflow-hidden">
    <div
      class="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,_var(--color-brand-100)_0%,_transparent_55%),radial-gradient(ellipse_at_bottom_left,_var(--color-brand-50)_0%,_transparent_50%)]"
      aria-hidden="true"
    />
    <div class="relative mx-auto flex max-w-6xl flex-col items-start gap-6 px-4 py-20 sm:px-6 sm:py-28">
      <p class="text-sm font-semibold uppercase tracking-[0.2em] text-brand-600">
        Restaurant platform
      </p>
      <h1 class="font-display max-w-2xl text-4xl font-semibold leading-tight text-brand-900 sm:text-5xl md:text-6xl">
        DineFlow
      </h1>
      <p class="max-w-xl text-lg leading-relaxed text-ink-muted">
        Ordering and restaurant management platform. Browse the demo menu with search,
        category filters, and detailed item pages.
      </p>
      <div class="flex flex-wrap items-center gap-3 pt-2">
        <NuxtLink
          to="/menu"
          class="inline-flex items-center justify-center rounded-lg bg-brand-700 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-brand-800"
        >
          Browse menu
        </NuxtLink>
        <span
          class="inline-flex items-center rounded-lg border border-brand-200 bg-surface-elevated px-4 py-2.5 text-sm text-ink-muted"
        >
          Health:
          <span
            class="ml-2 font-semibold"
            :class="healthOk ? 'text-brand-600' : 'text-ink-subtle'"
          >
            {{ healthLabel }}
          </span>
        </span>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
const config = useRuntimeConfig()
const apiUrl = config.public.apiUrl as string

const healthOk = ref(false)
const healthLabel = ref('checking…')

onMounted(async () => {
  try {
    const data = await $fetch<{ status: string }>(`${apiUrl}/api/v1/health`)
    healthOk.value = data.status === 'ok'
    healthLabel.value = healthOk.value ? 'ok' : 'unexpected'
  }
  catch {
    healthOk.value = false
    healthLabel.value = 'unreachable'
  }
})
</script>
