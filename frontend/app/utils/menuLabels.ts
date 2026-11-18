import type { MenuLabel } from '~/types/menu'
import { ALLERGENS } from '~/utils/allergens'

/**
 * Turn a label code into the words to show. Restaurants define their own allergens and dish types, so the lookup is
 * against their list first. An allergen the restaurant has since deleted, or a list that hasn't loaded yet, falls back
 * to the standard name (e.g. "milk" -> "Milk") and then to a readable form of the code — never a blank or an error.
 */
const STANDARD = Object.fromEntries(ALLERGENS.map(a => [a.code, a.label]))

export function labelText(labels: MenuLabel[], code: string, standard: Record<string, string> = {}): string {
  const found = labels.find(l => l.code === code)
  if (found) return found.label
  if (standard[code]) return standard[code]
  const words = code.replace(/_/g, ' ').trim()
  return words ? words.charAt(0).toUpperCase() + words.slice(1) : code
}

export const allergenText = (labels: MenuLabel[], code: string) => labelText(labels, code, STANDARD)
export const dishTypeText = (labels: MenuLabel[], code: string) => labelText(labels, code)
