import { describe, expect, it } from 'vitest'
import { clearPass, loadPass, savePass, TABLE_PASS_KEY } from '../app/utils/table-pass'

function fakeStore(initial: Record<string, string> = {}) {
  const data = { ...initial }
  return {
    data,
    getItem: (k: string) => data[k] ?? null,
    setItem: (k: string, v: string) => { data[k] = v },
    removeItem: (k: string) => { delete data[k] },
  }
}

const pass = { token: 't', sessionId: 4, tableToken: 'abc', restaurantId: 1 }

describe('table pass storage', () => {
  it('round-trips a pass for the same table and restaurant', () => {
    const store = fakeStore()
    savePass(store, pass)
    expect(loadPass(store, 'abc', 1)).toEqual(pass)
  })

  it('never offers a pass to another table or restaurant', () => {
    const store = fakeStore()
    savePass(store, pass)
    expect(loadPass(store, 'other', 1)).toBeNull()
    expect(loadPass(store, 'abc', 2)).toBeNull()
  })

  it('ignores junk and clears cleanly', () => {
    expect(loadPass(fakeStore({ [TABLE_PASS_KEY]: '{not json' }), 'abc', 1)).toBeNull()
    expect(loadPass(fakeStore({ [TABLE_PASS_KEY]: '{"token":5}' }), 'abc', 1)).toBeNull()
    const store = fakeStore()
    savePass(store, pass)
    clearPass(store)
    expect(loadPass(store, 'abc', 1)).toBeNull()
  })

  it('survives storage that throws', () => {
    const broken = { getItem: () => { throw new Error('x') }, setItem: () => { throw new Error('x') }, removeItem: () => { throw new Error('x') } }
    expect(() => savePass(broken, pass)).not.toThrow()
    expect(loadPass(broken, 'abc', 1)).toBeNull()
    expect(() => clearPass(broken)).not.toThrow()
  })
})
