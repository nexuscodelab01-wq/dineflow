import { usePosStore } from '../state/store';

/** `$12.50` — en-CA for Canada so Canadian dollars don't render as "CA$12.50". Falls back to a plain `$` if Intl can't. */
export function formatMoney(amount: number | string, currency: string, country: string): string {
  const value = Number(amount);
  try {
    return new Intl.NumberFormat(country === 'CA' ? 'en-CA' : 'en-US', { style: 'currency', currency: currency.toUpperCase() }).format(value);
  } catch {
    return `$${value.toFixed(2)}`;
  }
}

/** The restaurant's currency, learned at PIN login. */
export function useMoney(): (amount: number | string) => string {
  const currency = usePosStore((s) => s.currency);
  const country = usePosStore((s) => s.country);
  return (amount) => formatMoney(amount, currency, country);
}
