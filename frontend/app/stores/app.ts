import { defineStore } from 'pinia'

export const useAppStore = defineStore('app', {
  state: () => ({
    appName: 'DineFlow',
    initialized: true,
  }),
  getters: {
    title: (state) => state.appName,
  },
})
