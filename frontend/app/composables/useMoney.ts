import { formatCurrency } from '~/utils/format'

/**
 * `money(12.5)` in the currency of the restaurant being looked at: the one an admin is managing on /admin
 * pages (a platform admin can manage a restaurant other than the site's own), else this site's own.
 * Per-call state only — a module-level "active currency" would leak between tenants under SSR.
 */
export function useMoney() {
  const site = useRestaurantStore()
  const admin = useAdminStore()
  const route = useRoute()
  const money = (amount: number): string => {
    const r = route.path.startsWith('/admin') && admin.restaurant ? admin.restaurant : site.current
    return formatCurrency(amount, (r?.currency || 'usd').toUpperCase(), r?.country === 'CA' ? 'en-CA' : 'en-US')
  }
  return { money }
}
