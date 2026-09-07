import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAppStore } from '../app/stores/app'

describe('useAppStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('exposes DineFlow as the app title', () => {
    const store = useAppStore()
    expect(store.title).toBe('DineFlow')
    expect(store.initialized).toBe(true)
  })
})
