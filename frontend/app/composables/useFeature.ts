import { isFeatureOn } from '~/utils/features'

/** Reactive feature flag for this site's restaurant: `const booking = useFeature('reservations')`. */
export function useFeature(key: string) {
  const restaurant = useRestaurantStore()
  return computed(() => isFeatureOn(restaurant.current?.features, key))
}
