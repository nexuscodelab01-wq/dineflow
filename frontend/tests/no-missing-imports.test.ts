import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { describe, expect, it } from 'vitest'

/**
 * `@vueuse/nuxt` is not registered, so VueUse helpers are NOT auto-imported. A page that forgets the
 * import compiles and builds fine, then crashes at runtime ("useIntervalFn is not defined") —
 * which is how the customer order-tracking page broke unnoticed. Fail fast in CI instead.
 */
const HELPERS = [
  'useIntervalFn', 'useDebounceFn', 'useThrottleFn', 'useTimeoutFn', 'useStorage', 'useEventListener',
  'useNow', 'useClipboard', 'useMediaQuery', 'useWindowSize', 'useElementSize', 'useIntersectionObserver',
]

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name)
    if (statSync(path).isDirectory()) return sourceFiles(path)
    return /\.(vue|ts)$/.test(name) ? [path] : []
  })
}

describe('VueUse helpers are imported where used', () => {
  const root = join(__dirname, '..', 'app')
  for (const file of sourceFiles(root)) {
    const source = readFileSync(file, 'utf8')
    const used = HELPERS.filter(h => new RegExp(`\\b${h}\\s*\\(`).test(source))
    if (!used.length) continue
    it(relative(root, file), () => {
      for (const helper of used) {
        const imported = new RegExp(`import\\s*\\{[^}]*\\b${helper}\\b[^}]*\\}\\s*from\\s*['"]@vueuse/core['"]`).test(source)
        expect(imported, `${helper} is used but not imported from '@vueuse/core'`).toBe(true)
      }
    })
  }
})
