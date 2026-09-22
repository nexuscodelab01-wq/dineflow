import type { Closure, OpeningHours, OpenStatus } from '~/utils/hours'
import { openStatus, todaysHoursLabel } from '~/utils/hours'
import { wallClockIn } from '~/utils/timezone'

/** "Open now" / "Closed — opens 11:00" for the site's own restaurant, ticking over on its own. */
export function useOpeningStatus() {
  const restaurant = useRestaurantStore()
  const now = ref(new Date())

  let timer: ReturnType<typeof setInterval> | null = null
  onMounted(() => {
    timer = setInterval(() => { now.value = new Date() }, 60000)
  })
  onUnmounted(() => {
    if (timer) clearInterval(timer)
  })

  const status = computed<OpenStatus>(() => {
    const r = restaurant.current
    const local = wallClockIn(r?.timezone || 'UTC', now.value)
    return openStatus((r?.opening_hours as OpeningHours) ?? null, r?.closures as Closure[] | undefined, local)
  })

  const todayLabel = computed(() => {
    const r = restaurant.current
    return todaysHoursLabel((r?.opening_hours as OpeningHours) ?? null, wallClockIn(r?.timezone || 'UTC', now.value))
  })

  return { status, todayLabel }
}
