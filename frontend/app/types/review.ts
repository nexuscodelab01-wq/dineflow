export type EligibleVisit = {
  order_id?: number | null
  reservation_id?: number | null
  label: string
  visited_at: string
}

export type Review = {
  id: number
  order_id?: number | null
  reservation_id?: number | null
  rating: number
  comment?: string | null
  is_published: boolean
  staff_reply?: string | null
  staff_reply_at?: string | null
  created_at: string
}

export type PublicReview = {
  id: number
  reviewer_name: string
  rating: number
  comment?: string | null
  staff_reply?: string | null
  staff_reply_at?: string | null
  created_at: string
}

export type PublicReviewList = {
  items: PublicReview[]
  total: number
  page: number
  page_size: number
  pages: number
  average_rating: number | null
  counts_by_rating: Record<number, number>
}

export type AdminReview = {
  id: number
  reviewer_name: string
  reviewer_email?: string | null
  order_id?: number | null
  reservation_id?: number | null
  rating: number
  comment?: string | null
  is_published: boolean
  staff_reply?: string | null
  staff_reply_at?: string | null
  created_at: string
}
