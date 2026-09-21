import { describe, expect, it } from 'vitest'
import type { WaiterTable } from '../app/types/table'
import { attentionQueue, attentionReasons, needsAttention, planTables, transferTargets } from '../app/utils/waiter'

const table = (id: number, number: string, session: Partial<NonNullable<WaiterTable['session']>> | null, status = 'AVAILABLE'): WaiterTable => ({
  table_id: id, table_number: number, capacity: 4, shape: 'SQUARE', status: session ? 'OCCUPIED' : status,
  session: session ? { session_id: id * 10, opened_at: '2026-01-01T10:00:00Z', guests: 2, rounds: 1, ready_rounds: 0, total: '25.5', requests: [], waiting_since: null, ...session } : null,
})

describe('what needs a waiter', () => {
  it('flags a table with a request or finished food, not a quiet one', () => {
    expect(needsAttention(table(1, '1', { requests: ['WAITER'] }))).toBe(true)
    expect(needsAttention(table(1, '1', { ready_rounds: 2 }))).toBe(true)
    expect(needsAttention(table(1, '1', {}))).toBe(false)
    expect(needsAttention(table(1, '1', null))).toBe(false)
  })

  it('explains why, most urgent first', () => {
    expect(attentionReasons(table(1, '1', { requests: ['BILL', 'WAITER'], ready_rounds: 2 }))).toEqual(['Needs a waiter', 'Wants the bill', '2 rounds ready to serve'])
    expect(attentionReasons(table(1, '1', { ready_rounds: 1 }))).toEqual(['Food ready to serve'])
    expect(attentionReasons(table(1, '1', null))).toEqual([])
  })

  it('queues the longest-waiting request first, then food that is just ready', () => {
    const queue = attentionQueue([
      table(1, '1', { ready_rounds: 1 }),
      table(2, '2', { requests: ['WAITER'], waiting_since: '2026-01-01T10:05:00Z' }),
      table(3, '3', { requests: ['BILL'], waiting_since: '2026-01-01T10:01:00Z' }),
      table(4, '4', {}),
    ])
    expect(queue.map(t => t.table_number)).toEqual(['3', '2', '1'])
  })
})

describe('the floor plan', () => {
  it('shows a tab total on an occupied table and glows when it needs someone', () => {
    const [quiet, busy, free] = planTables([table(1, '1', {}), table(2, '2', { requests: ['WAITER'] }), table(3, '3', null)])
    expect([quiet!.state, quiet!.badge]).toEqual(['OCCUPIED', '$25.50'])
    expect([busy!.state, busy!.note]).toContain('ATTENTION')
    expect(busy!.note).toContain('Needs a waiter')
    expect([free!.state, free!.badge]).toEqual(['AVAILABLE', undefined])
  })

  it('keeps reserved and cleaning tables as they are and lets every table be tapped', () => {
    const plan = planTables([table(1, '1', null, 'RESERVED'), table(2, '2', null, 'CLEANING')])
    expect(plan.map(t => t.state)).toEqual(['RESERVED', 'CLEANING'])
    expect(plan.every(t => t.selectable)).toBe(true)
  })
})

describe('moving a tab', () => {
  it('offers only free tables other than the current one', () => {
    const tables = [table(1, '1', {}), table(2, '2', null), table(3, '3', {}), table(4, '4', null, 'RESERVED'), table(5, '5', null, 'CLEANING')]
    expect(transferTargets(tables, 1).map(t => t.table_number)).toEqual(['2', '5'])
  })
})
