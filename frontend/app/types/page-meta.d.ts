declare module '#app' {
  interface PageMeta {
    /** The feature flag this page belongs to; with it off the page behaves as if it doesn't exist (see middleware/feature.global.ts). */
    feature?: string | string[]
  }
}

export {}
