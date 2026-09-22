/** Turns one brand colour into the ten-step `brand` palette the site is styled with, keeping text readable. */

export const BRAND_STEPS = [50, 100, 200, 300, 400, 500, 600, 700, 800, 900] as const
export type Palette = Record<(typeof BRAND_STEPS)[number], string>

const HEX = /^#[0-9a-f]{6}$/i
const MIN_CONTRAST = 4.5 // WCAG AA for normal text: white text on brand-600 buttons must reach this

export function isHexColor(value: unknown): value is string {
  return typeof value === 'string' && HEX.test(value)
}

type Hsl = { h: number, s: number, l: number } // h 0-360, s and l 0-100

function hexToRgb(hex: string): [number, number, number] {
  return [1, 3, 5].map(i => Number.parseInt(hex.slice(i, i + 2), 16)) as [number, number, number]
}

function rgbToHex([r, g, b]: [number, number, number]): string {
  return `#${[r, g, b].map(v => Math.round(Math.min(255, Math.max(0, v))).toString(16).padStart(2, '0')).join('')}`
}

export function hexToHsl(hex: string): Hsl {
  const [r, g, b] = hexToRgb(hex).map(v => v / 255) as [number, number, number]
  const max = Math.max(r, g, b)
  const min = Math.min(r, g, b)
  const l = (max + min) / 2
  const d = max - min
  if (d === 0) return { h: 0, s: 0, l: l * 100 }
  const s = d / (1 - Math.abs(2 * l - 1))
  let h = max === r ? ((g - b) / d) % 6 : max === g ? (b - r) / d + 2 : (r - g) / d + 4
  h = (h * 60 + 360) % 360
  return { h, s: s * 100, l: l * 100 }
}

export function hslToHex({ h, s, l }: Hsl): string {
  const sat = s / 100
  const light = l / 100
  const c = (1 - Math.abs(2 * light - 1)) * sat
  const x = c * (1 - Math.abs(((h / 60) % 2) - 1))
  const m = light - c / 2
  const [r, g, b] = h < 60 ? [c, x, 0] : h < 120 ? [x, c, 0] : h < 180 ? [0, c, x] : h < 240 ? [0, x, c] : h < 300 ? [x, 0, c] : [c, 0, x]
  return rgbToHex([(r + m) * 255, (g + m) * 255, (b + m) * 255])
}

function luminance(hex: string): number {
  const [r, g, b] = hexToRgb(hex).map((v) => {
    const c = v / 255
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
  }) as [number, number, number]
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

/** WCAG contrast ratio between two colours (1 to 21). */
export function contrastRatio(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number]
  return (hi + 0.05) / (lo + 0.05)
}

/**
 * Build the palette around `base`. brand-600 (buttons, links) is the base colour, darkened only as far as
 * needed for white text on it to be readable. `adjusted` tells the caller the colour was changed.
 */
export function makePalette(base: string): { palette: Palette, adjusted: boolean } | null {
  if (!isHexColor(base)) return null
  const hsl = hexToHsl(base)
  let l600 = Math.min(hsl.l, 52)
  while (l600 > 12 && contrastRatio(hslToHex({ ...hsl, l: l600 }), '#ffffff') < MIN_CONTRAST) l600 -= 1

  const soft = Math.min(hsl.s, 55) // pale tints look muddy at full saturation
  const stop = (l: number, s = hsl.s): string => hslToHex({ h: hsl.h, s, l: Math.min(98, Math.max(6, l)) })
  const palette: Palette = {
    50: stop(96, soft),
    100: stop(91, soft),
    200: stop(83, soft),
    300: stop(72, hsl.s),
    400: stop(Math.max(l600 + 16, 60), hsl.s),
    500: stop(l600 + 7),
    600: stop(l600),
    700: stop(l600 - 7),
    800: stop(l600 - 14),
    900: stop(l600 - 20),
  }
  return { palette, adjusted: Math.abs(l600 - hsl.l) > 0.5 && hsl.l > l600 }
}

/**
 * CSS that re-colours the site. Only ever built from validated hex values, so it is safe to inline.
 * `accent` is optional — a restaurant with only a primary colour keeps the default accent (amber).
 */
export function paletteCss(base: string | null | undefined, accent?: string | null): string {
  const brand = base ? makePalette(base) : null
  const accentResult = accent ? makePalette(accent) : null
  if (!brand && !accentResult) return ''
  const vars = [
    ...(brand ? BRAND_STEPS.map(step => `--color-brand-${step}:${brand.palette[step]}`) : []),
    ...(accentResult ? BRAND_STEPS.map(step => `--color-accent-${step}:${accentResult.palette[step]}`) : []),
  ].join(';')
  return `html:root{${vars}}`
}
