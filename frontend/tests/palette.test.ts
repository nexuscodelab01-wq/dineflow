import { describe, expect, it } from 'vitest'
import { contrastRatio, hexToHsl, isHexColor, makePalette, paletteCss } from '../app/utils/palette'

describe('palette', () => {
  it('accepts only #rrggbb', () => {
    expect(isHexColor('#c0392b')).toBe(true)
    for (const bad of ['c0392b', '#c03', '#gggggg', 'red', '#c0392b;}', '', null, undefined, 5]) expect(isHexColor(bad)).toBe(false)
  })

  it('keeps white text readable on brand-600, whatever colour is chosen', () => {
    for (const color of ['#c0392b', '#2c6f53', '#1e88e5', '#f1c40f', '#ffe066', '#ffffff', '#000000', '#7f8c8d', '#ff00ff']) {
      const { palette } = makePalette(color)!
      expect(contrastRatio(palette[600], '#ffffff'), color).toBeGreaterThanOrEqual(4.5)
    }
  })

  it('leaves a colour that is already dark enough alone, and darkens one that is not', () => {
    const dark = makePalette('#255944')!
    expect(dark.adjusted).toBe(false)
    expect(Math.abs(hexToHsl(dark.palette[600]).l - hexToHsl('#255944').l)).toBeLessThan(1)
    const bright = makePalette('#f1c40f')!
    expect(bright.adjusted).toBe(true)
    expect(hexToHsl(bright.palette[600]).l).toBeLessThan(hexToHsl('#f1c40f').l)
  })

  it('goes from light to dark and keeps the hue', () => {
    const { palette } = makePalette('#1e88e5')!
    const lightness = [50, 100, 200, 300, 400, 500, 600, 700, 800, 900].map(s => hexToHsl(palette[s as 50]).l)
    for (let i = 1; i < lightness.length; i++) expect(lightness[i]).toBeLessThanOrEqual(lightness[i - 1]!)
    expect(Math.abs(hexToHsl(palette[600]).h - hexToHsl('#1e88e5').h)).toBeLessThan(4)
  })

  it('builds CSS variables only from valid colours', () => {
    expect(paletteCss('#c0392b')).toMatch(/^html:root\{(--color-brand-\d+:#[0-9a-f]{6};?){10}\}$/)
    expect(paletteCss('#c0392b;}body{display:none')).toBe('')
    expect(paletteCss(null)).toBe('')
  })
})
