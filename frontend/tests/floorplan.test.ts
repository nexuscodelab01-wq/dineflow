import { describe, expect, it } from 'vitest'
import {
  PLAN_H,
  PLAN_W,
  findFreeSpot,
  normalizeShape,
  seatPoints,
  tableMargin,
  tableSize,
  withLayout,
  zonesOf,
} from '../app/utils/floorplan'

describe('floor plan geometry', () => {
  it('draws bigger parties at bigger tables, and long tables wider than tall', () => {
    expect(tableSize('SQUARE', 8).w).toBeGreaterThan(tableSize('SQUARE', 2).w)
    const rect = tableSize('RECT', 6)
    expect(rect.w).toBeGreaterThan(rect.h)
    expect(tableSize('ROUND', 4)).toEqual({ w: tableSize('ROUND', 4).w, h: tableSize('ROUND', 4).w })
  })

  it('falls back to a square for unknown shapes', () => {
    expect(normalizeShape('TRIANGLE')).toBe('SQUARE')
    expect(normalizeShape(undefined)).toBe('SQUARE')
    expect(normalizeShape('ROUND')).toBe('ROUND')
  })

  it('places one seat per guest, evenly around a round table', () => {
    const seats = seatPoints('ROUND', 6)
    expect(seats).toHaveLength(6)
    const radii = seats.map(p => Math.hypot(p.x, p.y))
    for (const r of radii) expect(r).toBeCloseTo(radii[0]!, 6)
  })

  it('keeps seats for square and long tables outside the table edge', () => {
    for (const shape of ['SQUARE', 'RECT']) {
      const { w, h } = tableSize(shape, 8)
      const seats = seatPoints(shape, 8)
      expect(seats).toHaveLength(8)
      for (const s of seats) {
        const outside = Math.abs(s.x) > w / 2 - 1e-6 || Math.abs(s.y) > h / 2 - 1e-6
        expect(outside).toBe(true)
      }
    }
    expect(seatPoints('SQUARE', 0)).toEqual([])
  })

  it('lays out tables that were never placed so none overlap and all stay on the plan', () => {
    const tables = Array.from({ length: 11 }, (_, i) => ({ id: i, pos_x: null, pos_y: null }))
    const laid = withLayout(tables)
    for (const t of laid) {
      expect(t.x).toBeGreaterThan(0)
      expect(t.x).toBeLessThan(100)
      expect(t.y).toBeGreaterThan(0)
      expect(t.y).toBeLessThan(100)
    }
    expect(new Set(laid.map(t => `${t.x.toFixed(1)},${t.y.toFixed(1)}`)).size).toBe(11)
  })

  it('keeps placed tables where they are and puts new ones along the bottom', () => {
    const laid = withLayout([
      { id: 1, pos_x: 30, pos_y: 40 },
      { id: 2, pos_x: null, pos_y: null },
    ])
    expect(laid[0]).toMatchObject({ x: 30, y: 40 })
    expect(laid[1]!.y).toBeGreaterThan(85)
  })

  it('finds a free spot for a new table away from existing ones', () => {
    const existing = [{ x: 12, y: 20 }, { x: 25, y: 20 }]
    const spot = findFreeSpot(existing)
    for (const p of existing) {
      const d = Math.hypot(((p.x - spot.x) / 100) * PLAN_W, ((p.y - spot.y) / 100) * PLAN_H)
      expect(d).toBeGreaterThanOrEqual(14)
    }
  })

  it('reports how much room a table needs at the plan edge', () => {
    const m = tableMargin('ROUND', 10)
    expect(m.x).toBeGreaterThan(0)
    expect(m.x).toBeLessThan(50)
  })

  it('lists distinct zones alphabetically', () => {
    expect(zonesOf([{ zone: 'Patio' }, { zone: 'Bar' }, { zone: null }, { zone: 'Patio' }])).toEqual(['Bar', 'Patio'])
  })
})
