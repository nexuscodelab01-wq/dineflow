export type CouponDiscountType = 'PERCENT' | 'FIXED'

export type Coupon = {
  id: number
  code: string
  description?: string | null
  discount_type: CouponDiscountType
  discount_value: string
  min_order_amount?: string | null
  max_discount_amount?: string | null
  starts_at?: string | null
  ends_at?: string | null
  max_redemptions?: number | null
  max_per_customer?: number | null
  times_redeemed: number
  is_active: boolean
  created_at: string
}

export type CouponCreatePayload = {
  code: string
  description?: string
  discount_type: CouponDiscountType
  discount_value: string
  min_order_amount?: string
  max_discount_amount?: string
  starts_at?: string
  ends_at?: string
  max_redemptions?: number
  max_per_customer?: number
}

/** Advisory only — the server recomputes the real discount when the order is placed. */
export type CouponPreview = {
  code: string
  description?: string | null
  discount: string
}
