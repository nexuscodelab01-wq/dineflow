/**
 * The 14 allergens the UK/EU require food businesses to declare ("Natasha's Law" / FIC).
 * Mirrors `backend/app/core/allergens.py` — codes must match exactly, since they're stored as-is.
 */
export const ALLERGENS = [
  { code: 'celery', label: 'Celery' },
  { code: 'cereals_gluten', label: 'Cereals containing gluten' },
  { code: 'crustaceans', label: 'Crustaceans' },
  { code: 'eggs', label: 'Eggs' },
  { code: 'fish', label: 'Fish' },
  { code: 'lupin', label: 'Lupin' },
  { code: 'milk', label: 'Milk' },
  { code: 'molluscs', label: 'Molluscs' },
  { code: 'mustard', label: 'Mustard' },
  { code: 'nuts', label: 'Tree nuts' },
  { code: 'peanuts', label: 'Peanuts' },
  { code: 'sesame', label: 'Sesame' },
  { code: 'soybeans', label: 'Soybeans' },
  { code: 'sulphites', label: 'Sulphur dioxide / sulphites' },
] as const

const LABELS: Record<string, string> = Object.fromEntries(ALLERGENS.map(a => [a.code, a.label]))

export function allergenLabel(code: string): string {
  return LABELS[code] ?? code
}
