import type { MenuLabel } from '~/types/menu'
import { fetchMenuLabels } from '~/services/menu'
import { allergenText, dishTypeText } from '~/utils/menuLabels'

/**
 * The restaurant's own allergens and dish types, loaded once and shared by every screen that names them
 * (menu cards, dish page, filters, kitchen tickets, the admin menu). Call `load(restaurantId)` where the list
 * is needed; the text helpers work before it finishes, falling back to the standard names.
 */
export function useMenuLabels() {
  const labels = useState<MenuLabel[]>('menuLabels', () => [])
  const loadedFor = useState<number | null>('menuLabelsFor', () => null)

  async function load(restaurantId: number, force = false) {
    if (!force && loadedFor.value === restaurantId) return
    try {
      labels.value = await fetchMenuLabels(restaurantId)
      loadedFor.value = restaurantId
    }
    catch {
      // Labels are decoration on a dish: if they can't load, the menu still works with the fallback names.
    }
  }

  return {
    labels,
    allergens: computed(() => labels.value.filter(l => l.kind === 'allergen')),
    dishTypes: computed(() => labels.value.filter(l => l.kind === 'dish_type')),
    load,
    allergenLabel: (code: string) => allergenText(labels.value, code),
    tagLabel: (code: string) => dishTypeText(labels.value, code),
  }
}
