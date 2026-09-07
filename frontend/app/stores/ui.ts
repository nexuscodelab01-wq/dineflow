import { defineStore } from 'pinia'

export type ToastType = 'success' | 'error' | 'info'

export type Toast = {
  id: number
  message: string
  type: ToastType
}

export type ConfirmOptions = {
  title: string
  message: string
  confirmLabel?: string
  cancelLabel?: string
  destructive?: boolean
}

type PendingConfirm = ConfirmOptions & {
  resolve: (confirmed: boolean) => void
}

let toastId = 0

export const useUiStore = defineStore('ui', {
  state: () => ({
    toasts: [] as Toast[],
    confirm: null as PendingConfirm | null,
  }),

  actions: {
    toast(message: string, type: ToastType = 'info', durationMs = 4000) {
      const id = ++toastId
      this.toasts.push({ id, message, type })
      if (durationMs > 0) {
        setTimeout(() => this.dismissToast(id), durationMs)
      }
    },

    success(message: string) {
      this.toast(message, 'success')
    },

    error(message: string) {
      this.toast(message, 'error', 6000)
    },

    dismissToast(id: number) {
      this.toasts = this.toasts.filter(t => t.id !== id)
    },

    confirm(options: ConfirmOptions): Promise<boolean> {
      return new Promise((resolve) => {
        this.confirm = { ...options, resolve }
      })
    },

    answerConfirm(confirmed: boolean) {
      if (!this.confirm) return
      this.confirm.resolve(confirmed)
      this.confirm = null
    },
  },
})
