/** A device's pass to one table session, kept in the browser so a refresh doesn't lose the tab. */

export type TablePass = {
  token: string
  sessionId: number
  /** The QR token it was issued for: a pass is only used on that table's page. */
  tableToken: string
  restaurantId: number
}

type Store = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>

export const TABLE_PASS_KEY = 'dineflow.table-pass'

export function savePass(store: Store, pass: TablePass): void {
  try {
    store.setItem(TABLE_PASS_KEY, JSON.stringify(pass))
  }
  catch { /* private mode: the pass just lasts until the page is closed */ }
}

export function loadPass(store: Store, tableToken: string, restaurantId: number): TablePass | null {
  try {
    const raw = store.getItem(TABLE_PASS_KEY)
    if (!raw) return null
    const pass = JSON.parse(raw) as Partial<TablePass>
    const valid = typeof pass.token === 'string' && typeof pass.sessionId === 'number'
    // A pass for another table or restaurant must never be sent along with this page's requests.
    return valid && pass.tableToken === tableToken && pass.restaurantId === restaurantId ? pass as TablePass : null
  }
  catch {
    return null
  }
}

export function clearPass(store: Store): void {
  try {
    store.removeItem(TABLE_PASS_KEY)
  }
  catch { /* nothing to clear */ }
}
