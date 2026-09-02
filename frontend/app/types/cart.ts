export type CartLineModifier = {
  option_id: number
  modifier_name: string
  option_name: string
  price_adjustment: number
}

export type CartLine = {
  id: string
  menu_item_id: number
  name: string
  image_url?: string | null
  unit_price: number
  quantity: number
  modifier_option_ids: number[]
  modifiers: CartLineModifier[]
  special_instructions?: string
}

export type CartTotals = {
  subtotal: number
  tax: number
  delivery_fee: number
  discount: number
  total: number
}
