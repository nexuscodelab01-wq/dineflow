/** Is a feature flag on? Unknown or not-yet-loaded flags count as off, so nothing half-finished shows by accident. */
export function isFeatureOn(features: Record<string, boolean> | null | undefined, key: string): boolean {
  return features?.[key] === true
}

/** Is at least one of these flags on? A page that several features share (the kitchen, the order list) only goes away when ALL of them are off. */
export function anyFeatureOn(features: Record<string, boolean> | null | undefined, keys: string | string[]): boolean {
  return (Array.isArray(keys) ? keys : [keys]).some(key => isFeatureOn(features, key))
}

/** The ways a restaurant can take an order. The kitchen and the order list serve all of them. */
export const ORDERING_CHANNELS = ['online_ordering', 'pos', 'qr_table_ordering']

/** A customer account only has a purpose while one of these is on: they order, book a table, earn points or write a review. */
export const CUSTOMER_ACCOUNT_FEATURES = ['online_ordering', 'reservations', 'loyalty', 'reviews']
