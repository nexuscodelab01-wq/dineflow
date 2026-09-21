/** Is a feature flag on? Unknown or not-yet-loaded flags count as off, so nothing half-finished shows by accident. */
export function isFeatureOn(features: Record<string, boolean> | null | undefined, key: string): boolean {
  return features?.[key] === true
}
