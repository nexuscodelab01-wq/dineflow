import { loadStripe, type Stripe } from '@stripe/stripe-js'

// One Stripe.js instance per connected account — which account it can confirm a payment for is fixed
// at initialisation (`stripeAccount`), so a customer moving between restaurants in one browser session
// (unlikely, but two tabs can) must not share an instance.
const byAccount = new Map<string, Promise<Stripe | null>>()

/** Stripe.js scoped to one restaurant's connected account (a *direct* charge — see stripe_provider.py).
 * Resolves to null when no publishable key is configured yet (payments not set up on this platform). */
export function getStripe(connectedAccountId: string): Promise<Stripe | null> {
  const key = useRuntimeConfig().public.stripePublishableKey as string
  if (!key) return Promise.resolve(null)
  if (!byAccount.has(connectedAccountId)) {
    byAccount.set(connectedAccountId, loadStripe(key, { stripeAccount: connectedAccountId }))
  }
  return byAccount.get(connectedAccountId)!
}
