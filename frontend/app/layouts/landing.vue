<script setup lang="ts">
// The frame for the platform's own front door (the bare domain, where no restaurant lives).
</script>

<template>
  <div class="flex min-h-screen flex-col bg-surface text-ink">
    <header class="border-b border-brand-100 bg-surface-elevated">
      <div class="mx-auto flex max-w-6xl items-center justify-between px-4 py-4 sm:px-6">
        <span class="font-display text-xl font-semibold text-brand-800">DineFlow</span>
        <NuxtLink to="/login" class="rounded-full border border-brand-200 px-4 py-2 text-sm font-semibold text-brand-800 hover:bg-brand-50">Restaurant sign in</NuxtLink>
      </div>
    </header>
    <main class="flex-1"><slot /></main>
    <footer class="border-t border-brand-100 bg-surface-elevated py-6 text-center text-xs text-ink-subtle">
      © {{ new Date().getFullYear() }} DineFlow
    </footer>
  </div>
</template>
