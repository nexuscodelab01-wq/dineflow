<script setup lang="ts">
const ui = useUiStore()
</script>

<template>
  <Teleport to="body">
    <div
      v-if="ui.confirm"
      class="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 px-4"
      role="dialog"
      aria-modal="true"
    >
      <div class="w-full max-w-md rounded-2xl border border-brand-100 bg-surface-elevated p-6 shadow-xl">
        <h2 class="font-display text-lg font-semibold text-brand-900">{{ ui.confirm.title }}</h2>
        <p class="mt-2 text-sm text-ink-muted">{{ ui.confirm.message }}</p>
        <div class="mt-6 flex justify-end gap-3">
          <button
            type="button"
            class="rounded-lg px-4 py-2 text-sm font-medium text-ink-muted hover:bg-brand-50"
            @click="ui.answerConfirm(false)"
          >
            {{ ui.confirm.cancelLabel || 'Cancel' }}
          </button>
          <button
            type="button"
            class="rounded-lg px-4 py-2 text-sm font-semibold text-white"
            :class="ui.confirm.destructive ? 'bg-red-600 hover:bg-red-700' : 'bg-brand-700 hover:bg-brand-800'"
            @click="ui.answerConfirm(true)"
          >
            {{ ui.confirm.confirmLabel || 'Confirm' }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
