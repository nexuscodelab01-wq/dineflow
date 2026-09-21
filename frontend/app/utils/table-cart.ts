/** The items a guest has picked but not yet sent to the kitchen. Pure functions so the rules are testable. */

export type TableLine = {
  key: string
  menuItemId: number
  name: string
  unitPrice: number
  quantity: number
  optionIds: number[]
  optionNames: string[]
  instructions?: string
}

export const MAX_LINE_QUANTITY = 20

const keyOf = (menuItemId: number, optionIds: number[], instructions?: string) =>
  `${menuItemId}:${[...optionIds].sort((a, b) => a - b).join(',')}:${(instructions ?? '').trim().toLowerCase()}`

/** Add a line; the same dish with the same options and note just increases the quantity. */
export function addLine(lines: TableLine[], line: Omit<TableLine, 'key'>): TableLine[] {
  const key = keyOf(line.menuItemId, line.optionIds, line.instructions)
  const existing = lines.find(l => l.key === key)
  if (!existing) return [...lines, { ...line, instructions: line.instructions?.trim() || undefined, key, quantity: Math.min(line.quantity, MAX_LINE_QUANTITY) }]
  return lines.map(l => (l.key === key ? { ...l, quantity: Math.min(l.quantity + line.quantity, MAX_LINE_QUANTITY) } : l))
}

/** Change a line's quantity by `delta`; reaching zero removes it. */
export function changeQuantity(lines: TableLine[], key: string, delta: number): TableLine[] {
  return lines
    .map(l => (l.key === key ? { ...l, quantity: Math.min(l.quantity + delta, MAX_LINE_QUANTITY) } : l))
    .filter(l => l.quantity > 0)
}

export const lineCount = (lines: TableLine[]) => lines.reduce((n, l) => n + l.quantity, 0)

/** Estimated subtotal in cents-safe arithmetic (the server's figure, with tax, is the one that counts). */
export function subtotal(lines: TableLine[]): number {
  return lines.reduce((sum, l) => sum + Math.round(l.unitPrice * 100) * l.quantity, 0) / 100
}

export function toRoundPayload(lines: TableLine[], notes?: string) {
  return {
    items: lines.map(l => ({
      menu_item_id: l.menuItemId,
      quantity: l.quantity,
      modifier_option_ids: l.optionIds,
      special_instructions: l.instructions ?? null,
    })),
    notes: notes?.trim() || null,
  }
}
