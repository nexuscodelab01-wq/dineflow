/**
 * Floor-plan geometry, shared by the customer seating plan and the admin editor.
 *
 * The plan is an SVG with a 160×100 viewBox. Tables store their position as a percentage of
 * the plan's width/height (0–100), so the same layout scales to any screen.
 */

export type TableShape = 'ROUND' | 'SQUARE' | 'RECT'

export const PLAN_W = 160
export const PLAN_H = 100
export const SEAT_RADIUS = 1.4
const SEAT_GAP = 1.9

export const SHAPES: { value: TableShape, label: string }[] = [
  { value: 'ROUND', label: 'Round' },
  { value: 'SQUARE', label: 'Square' },
  { value: 'RECT', label: 'Long' },
]

/** Suggested seating areas — free text is still allowed. */
export const ZONE_PRESETS = ['Window', 'Center', 'Bar', 'Patio', 'Booth', 'Private room']

export const UNASSIGNED_ZONE = 'No zone'

export type PlanTable = {
  id: number
  table_number: string
  capacity: number
  zone?: string | null
  shape?: TableShape | string | null
  pos_x?: number | null
  pos_y?: number | null
  /** Drives the colour: AVAILABLE, UNAVAILABLE, TOO_SMALL, RESERVED, OCCUPIED, CLEANING, INACTIVE or NEUTRAL. */
  state: string
  /** Overrides whether the table can be picked (defaults to state === 'AVAILABLE'). */
  selectable?: boolean
  /** Tooltip / screen-reader detail. */
  note?: string
  /** Short text drawn under the table number instead of the seat count (e.g. a tab total). */
  badge?: string
}

export function normalizeShape(shape?: string | null): TableShape {
  return shape === 'ROUND' || shape === 'RECT' ? shape : 'SQUARE'
}

/** Drawn size in viewBox units — bigger parties get bigger tables. */
export function tableSize(shape: string | null | undefined, capacity: number): { w: number, h: number } {
  const seats = Math.max(1, capacity)
  if (normalizeShape(shape) === 'RECT') return { w: 9 + seats * 1.5, h: 7 }
  const side = 6.5 + seats * 0.9
  return { w: side, h: side }
}

/** Seat centres relative to the table centre, spread evenly around it. */
export function seatPoints(shape: string | null | undefined, capacity: number): { x: number, y: number }[] {
  const n = Math.max(0, Math.min(capacity, 20))
  const { w, h } = tableSize(shape, capacity)
  const points: { x: number, y: number }[] = []

  if (normalizeShape(shape) === 'ROUND') {
    const r = w / 2 + SEAT_GAP
    for (let i = 0; i < n; i++) {
      const angle = (i / n) * Math.PI * 2 - Math.PI / 2
      points.push({ x: Math.cos(angle) * r, y: Math.sin(angle) * r })
    }
    return points
  }

  // Square / long tables: walk the perimeter of a rectangle just outside the table edge.
  const hw = w / 2 + SEAT_GAP
  const hh = h / 2 + SEAT_GAP
  const perimeter = 4 * (hw + hh)
  for (let i = 0; i < n; i++) {
    let d = ((i + 0.5) / n) * perimeter
    if (d < 2 * hw) {
      points.push({ x: -hw + d, y: -hh }) // top, left → right
      continue
    }
    d -= 2 * hw
    if (d < 2 * hh) {
      points.push({ x: hw, y: -hh + d }) // right, top → bottom
      continue
    }
    d -= 2 * hh
    if (d < 2 * hw) {
      points.push({ x: hw - d, y: hh }) // bottom, right → left
      continue
    }
    d -= 2 * hw
    points.push({ x: -hw, y: hh - d }) // left, bottom → top
  }
  return points
}

export function clampPercent(value: number, min = 0, max = 100): number {
  return Math.min(max, Math.max(min, value))
}

/** Half-extent of a table (plus its seats) as a percentage of the plan, for keeping it on canvas. */
export function tableMargin(shape: string | null | undefined, capacity: number): { x: number, y: number } {
  const { w, h } = tableSize(shape, capacity)
  return {
    x: ((w / 2 + SEAT_GAP + SEAT_RADIUS) / PLAN_W) * 100,
    y: ((h / 2 + SEAT_GAP + SEAT_RADIUS) / PLAN_H) * 100,
  }
}

type Placeable = { pos_x?: number | null, pos_y?: number | null }

/**
 * Give every table a position. Tables that were never placed (older data) are laid out
 * automatically so the plan is never empty: in a grid when none are placed, otherwise along
 * the bottom edge.
 */
export function withLayout<T extends Placeable>(tables: T[]): (T & { x: number, y: number })[] {
  const isPlaced = (t: T) => t.pos_x != null && t.pos_y != null
  const unplaced = tables.filter(t => !isPlaced(t))
  const slots = new Map<T, { x: number, y: number }>()

  if (unplaced.length === tables.length) {
    const cols = Math.max(1, Math.ceil(Math.sqrt(unplaced.length * 1.6)))
    const rows = Math.ceil(unplaced.length / cols)
    unplaced.forEach((t, i) => {
      slots.set(t, {
        x: ((i % cols) + 0.5) * (100 / cols),
        y: 12 + (Math.floor(i / cols) + 0.5) * (76 / rows),
      })
    })
  }
  else {
    unplaced.forEach((t, i) => {
      slots.set(t, { x: 8 + (i % 6) * 15, y: 93 - Math.floor(i / 6) * 12 })
    })
  }

  return tables.map(t => ({ ...t, ...(isPlaced(t) ? { x: t.pos_x as number, y: t.pos_y as number } : slots.get(t)!) }))
}

/** A spot for a new table that doesn't sit on top of existing ones. */
export function findFreeSpot(existing: { x: number, y: number }[], minGap = 14): { x: number, y: number } {
  for (let y = 20; y <= 85; y += 13) {
    for (let x = 12; x <= 90; x += 13) {
      // Percent units are not square (the plan is wider than tall), so compare in viewBox units.
      const clear = existing.every(p => Math.hypot(((p.x - x) / 100) * PLAN_W, ((p.y - y) / 100) * PLAN_H) >= minGap)
      if (clear) return { x, y }
    }
  }
  return { x: 50, y: 50 }
}

export function zonesOf(tables: { zone?: string | null }[]): string[] {
  const seen = new Set<string>()
  for (const t of tables) if (t.zone) seen.add(t.zone)
  return [...seen].sort((a, b) => a.localeCompare(b))
}

export const STATE_LABELS: Record<string, string> = {
  AVAILABLE: 'Available',
  UNAVAILABLE: 'Taken',
  TOO_SMALL: 'Too small',
  RESERVED: 'Reserved',
  OCCUPIED: 'Occupied',
  ATTENTION: 'Needs you',
  CLEANING: 'Cleaning',
  INACTIVE: 'Out of service',
  NEUTRAL: 'Table',
}

export const STATE_STYLES: Record<string, { fill: string, stroke: string, text: string, opacity?: number, dashed?: boolean }> = {
  AVAILABLE: { fill: '#dcfce7', stroke: '#16a34a', text: '#14532d' },
  UNAVAILABLE: { fill: '#fef3c7', stroke: '#d97706', text: '#78350f' },
  RESERVED: { fill: '#fef3c7', stroke: '#d97706', text: '#78350f' },
  OCCUPIED: { fill: '#fee2e2', stroke: '#dc2626', text: '#7f1d1d' },
  ATTENTION: { fill: '#fde047', stroke: '#b45309', text: '#422006' },
  CLEANING: { fill: '#e2e8f0', stroke: '#64748b', text: '#334155' },
  TOO_SMALL: { fill: '#f3f4f6', stroke: '#9ca3af', text: '#6b7280', opacity: 0.65 },
  INACTIVE: { fill: '#f3f4f6', stroke: '#9ca3af', text: '#6b7280', opacity: 0.6, dashed: true },
  NEUTRAL: { fill: '#e7f3ed', stroke: '#3a8b68', text: '#1a3b2f' },
}
