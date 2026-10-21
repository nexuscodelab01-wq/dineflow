/** Stripe Tax product categories a dish can carry — mirrors `TAX_CODES` in backend/app/core/locale.py. */
export const TAX_CODES: Record<string, string> = {
  txcd_40060003: 'Prepared food (eat-in / hot food)',
  txcd_40040000: 'Grocery / packaged food',
  txcd_40040021: 'Plain bread',
  txcd_41020001: 'Alcohol — beer',
  txcd_41020002: 'Alcohol — spirits',
  txcd_41020003: 'Alcohol — wine',
}
