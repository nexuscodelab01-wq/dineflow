/** How the waiter's floor looks: which tables need someone, and how each is drawn. Pure, so it is testable. */
import type { WaiterTable } from '~/types/table'
import type { PlanTable } from '~/utils/floorplan'

export const needsAttention = (t: WaiterTable): boolean =>
  !!t.session && (t.session.requests.length > 0 || t.session.ready_rounds > 0)

/** "Waiter" / "Bill" / "Ready" reasons a table is flagged, most urgent first. */
export function attentionReasons(t: WaiterTable): string[] {
  const s = t.session
  if (!s) return []
  const out: string[] = []
  if (s.requests.includes('WAITER')) out.push('Needs a waiter')
  if (s.requests.includes('BILL')) out.push('Wants the bill')
  if (s.ready_rounds > 0) out.push(s.ready_rounds === 1 ? 'Food ready to serve' : `${s.ready_rounds} rounds ready to serve`)
  return out
}

const money = (value: string | number) => `$${Number(value).toFixed(2)}`

/** Tables as the floor plan draws them: a table with a tab shows its total, and glows when it needs someone. */
export function planTables(tables: WaiterTable[]): PlanTable[] {
  return tables.map((t) => {
    const reasons = attentionReasons(t)
    const state = t.session ? (reasons.length ? 'ATTENTION' : 'OCCUPIED') : t.status
    const note = [
      `Table ${t.table_number}, seats ${t.capacity}`,
      t.session ? `tab ${money(t.session.total)}, ${t.session.rounds} round${t.session.rounds === 1 ? '' : 's'}` : t.status.toLowerCase(),
      ...reasons,
    ].join(', ')
    return {
      id: t.table_id,
      table_number: t.table_number,
      capacity: t.capacity,
      zone: t.zone,
      shape: t.shape,
      pos_x: t.pos_x,
      pos_y: t.pos_y,
      state,
      selectable: true,
      note,
      badge: t.session ? money(t.session.total) : undefined,
    }
  })
}

/** Tables that need someone, longest-waiting first (requests, then ready food), for a quick list beside the map. */
export function attentionQueue(tables: WaiterTable[]): WaiterTable[] {
  return tables
    .filter(needsAttention)
    .sort((a, b) => {
      const wa = a.session?.waiting_since ? new Date(a.session.waiting_since).getTime() : Number.POSITIVE_INFINITY
      const wb = b.session?.waiting_since ? new Date(b.session.waiting_since).getTime() : Number.POSITIVE_INFINITY
      return wa - wb
    })
}

/** Free tables a tab could move to: active, no open tab, and not the one it is on. */
export function transferTargets(tables: WaiterTable[], currentTableId: number): WaiterTable[] {
  return tables.filter(t => t.table_id !== currentTableId && !t.session && t.status !== 'RESERVED')
}
