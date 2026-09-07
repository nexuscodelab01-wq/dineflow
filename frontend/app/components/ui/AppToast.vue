<script setup lang="ts">
const ui = useUiStore()

const typeStyles = {
  success: 'border-emerald-200 bg-emerald-50 text-emerald-900',
  error: 'border-red-200 bg-red-50 text-red-900',
  info: 'border-brand-200 bg-surface-elevated text-ink',
}
</script>

<template>
  <div class="pointer-events-none fixed inset-x-0 top-4 z-50 flex flex-col items-center gap-2 px-4">
    <TransitionGroup name="toast">
      <div
        v-for="toast in ui.toasts"
        :key="toast.id"
        class="pointer-events-auto w-full max-w-sm rounded-xl border px-4 py-3 text-sm shadow-lg"
        :class="typeStyles[toast.type]"
        role="status"
      >
        <div class="flex items-start justify-between gap-3">
          <p>{{ toast.message }}</p>
          <button
            type="button"
            class="shrink-0 text-xs font-medium opacity-70 hover:opacity-100"
            @click="ui.dismissToast(toast.id)"
          >
            Dismiss
          </button>
        </div>
      </div>
    </TransitionGroup>
  </div>
</template>

<style scoped>
.toast-enter-active,
.toast-leave-active {
  transition: all 0.2s ease;
}
.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}
</style>
