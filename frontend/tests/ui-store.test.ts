import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useUiStore } from '../app/stores/ui'

describe('useUiStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('queues and dismisses toasts', () => {
    const ui = useUiStore()
    ui.success('Saved')
    expect(ui.toasts).toHaveLength(1)
    expect(ui.toasts[0]?.message).toBe('Saved')
    ui.dismissToast(ui.toasts[0]!.id)
    expect(ui.toasts).toHaveLength(0)
  })

  it('resolves confirm dialog answers', async () => {
    const ui = useUiStore()
    const answer = ui.confirm({
      title: 'Delete item',
      message: 'Are you sure?',
    })
    expect(ui.confirmDialog?.title).toBe('Delete item')
    ui.answerConfirm(true)
    await expect(answer).resolves.toBe(true)
  })
})
