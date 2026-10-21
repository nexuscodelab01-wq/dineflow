/** `en-CA` matters: under `en-US` Canadian dollars render as "CA$12.50" instead of "$12.50". */
export function formatCurrency(amount: number, currency = 'USD', locale = 'en-US'): string {
  return new Intl.NumberFormat(locale, {
    style: 'currency',
    currency,
  }).format(amount)
}
