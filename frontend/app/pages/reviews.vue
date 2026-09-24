<script setup lang="ts">
import type { PublicReview } from '~/types/review'
import type { EligibleVisit, Review } from '~/types/review'
import { fetchEligibleVisits, fetchMyReviews, fetchPublicReviews, submitReview } from '~/services/reviews'

// Public hub: anyone can browse every published review here (not just their own) — the same list
// the home page teases a handful of. Signed-in customers additionally see their own completed
// visits to rate, and their own reviews, at the top.
const reviewsEnabled = useFeature('reviews')
const restaurant = useRestaurantStore()
const auth = useAuthStore()
const hydrated = useHydrated()
const signedIn = computed(() => hydrated.value && auth.isAuthenticated)

const publicReviews = ref<PublicReview[]>([])
const averageRating = ref<number | null>(null)
const totalReviews = ref(0)
const page = ref(1)
const pageSize = 10
const pages = ref(1)
const loadingPublic = ref(true)

const eligible = ref<EligibleVisit[]>([])
const mine = ref<Review[]>([])
const loadingMine = ref(false)

const openVisit = ref<EligibleVisit | null>(null)
const rating = ref(5)
const comment = ref('')
const submitting = ref(false)
const error = ref('')

// Your own review already shows under "Your reviews" above — drop it here so it isn't listed twice.
const otherReviews = computed(() => publicReviews.value.filter(pr => !mine.value.some(m => m.id === pr.id)))

async function loadPublic() {
  if (!restaurant.current) return
  loadingPublic.value = true
  try {
    const res = await fetchPublicReviews(restaurant.current.slug, page.value, pageSize)
    publicReviews.value = res.items
    averageRating.value = res.average_rating
    totalReviews.value = res.total
    pages.value = res.pages
  }
  finally {
    loadingPublic.value = false
  }
}

async function loadMine() {
  loadingMine.value = true
  try {
    const [e, r] = await Promise.all([fetchEligibleVisits(), fetchMyReviews()])
    eligible.value = e
    mine.value = r
  }
  finally {
    loadingMine.value = false
  }
}

onMounted(async () => {
  if (!reviewsEnabled.value) return
  await loadPublic()
})
watch(page, loadPublic)
watch(signedIn, (on) => { if (on) void loadMine() }, { immediate: true })

function start(visit: EligibleVisit) {
  openVisit.value = visit
  rating.value = 5
  comment.value = ''
  error.value = ''
}

async function submit() {
  if (!openVisit.value || submitting.value) return
  submitting.value = true
  error.value = ''
  try {
    await submitReview({
      order_id: openVisit.value.order_id ?? undefined,
      reservation_id: openVisit.value.reservation_id ?? undefined,
      rating: rating.value,
      comment: comment.value.trim() || undefined,
    })
    openVisit.value = null
    await Promise.all([loadMine(), loadPublic()])
  }
  catch (err) {
    error.value = err instanceof Error ? err.message : 'Could not submit your review'
  }
  finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="mx-auto max-w-2xl px-4 py-12 sm:px-6">
    <p class="text-sm font-semibold uppercase tracking-[0.2em] text-brand-600">Guest reviews</p>
    <h1 class="font-display mt-2 text-3xl font-semibold text-brand-900">Reviews</h1>
    <div v-if="averageRating" class="mt-2 flex items-center gap-2 text-sm text-ink-muted">
      <span class="flex text-amber-500">
        <svg v-for="n in 5" :key="n" viewBox="0 0 20 20" class="h-4 w-4" :fill="n <= Math.round(averageRating) ? 'currentColor' : 'none'" stroke="currentColor" stroke-width="1.2">
          <path d="M10 1.5l2.6 5.27 5.82.85-4.21 4.1 1 5.8L10 14.9l-5.21 2.62 1-5.8-4.21-4.1 5.82-.85z" stroke-linejoin="round" />
        </svg>
      </span>
      <span class="font-semibold text-ink">{{ averageRating }}</span> out of 5 · {{ totalReviews }} review{{ totalReviews === 1 ? '' : 's' }}
    </div>

    <p v-if="!reviewsEnabled" class="mt-8 text-sm text-ink-subtle">Reviews aren't available here yet.</p>

    <template v-else>
      <!-- Your own visits and reviews, only once we know who's signed in -->
      <template v-if="signedIn">
        <section v-if="eligible.length" class="mt-8">
          <h2 class="text-sm font-semibold uppercase tracking-wide text-ink-subtle">Leave a review</h2>
          <ul class="mt-3 space-y-3">
            <li
              v-for="visit in eligible" :key="`${visit.order_id ?? 'r'}-${visit.reservation_id ?? 'o'}`"
              class="flex items-center justify-between gap-3 rounded-2xl border border-brand-100 bg-surface-elevated p-4"
            >
              <div>
                <p class="font-medium text-ink">{{ visit.label }}</p>
                <p class="text-xs text-ink-subtle">{{ new Date(visit.visited_at).toLocaleDateString() }}</p>
              </div>
              <AppButton @click="start(visit)">Rate it</AppButton>
            </li>
          </ul>
        </section>

        <div v-if="openVisit" class="mt-6 rounded-2xl border border-brand-200 bg-surface-elevated p-5">
          <p class="font-semibold text-ink">{{ openVisit.label }}</p>
          <div class="mt-3 flex gap-1">
            <button
              v-for="n in 5" :key="n" type="button" class="text-amber-500" :aria-label="`${n} star${n === 1 ? '' : 's'}`"
              @click="rating = n"
            >
              <svg viewBox="0 0 20 20" class="h-7 w-7" :fill="n <= rating ? 'currentColor' : 'none'" stroke="currentColor" stroke-width="1.2">
                <path d="M10 1.5l2.6 5.27 5.82.85-4.21 4.1 1 5.8L10 14.9l-5.21 2.62 1-5.8-4.21-4.1 5.82-.85z" stroke-linejoin="round" />
              </svg>
            </button>
          </div>
          <textarea
            v-model="comment" rows="3" maxlength="2000" placeholder="Tell us how it went (optional)"
            class="mt-3 w-full rounded-lg border border-brand-200 px-3 py-2 text-sm"
          />
          <p v-if="error" class="mt-2 text-sm text-red-600" role="alert">{{ error }}</p>
          <div class="mt-3 flex gap-2">
            <AppButton :disabled="submitting" @click="submit">{{ submitting ? 'Submitting…' : 'Submit review' }}</AppButton>
            <button type="button" class="text-sm text-ink-subtle hover:underline" @click="openVisit = null">Cancel</button>
          </div>
        </div>

        <section v-if="mine.length" class="mt-10">
          <h2 class="text-sm font-semibold uppercase tracking-wide text-ink-subtle">Your reviews</h2>
          <ul class="mt-3 space-y-3">
            <li v-for="r in mine" :key="r.id" class="rounded-2xl border border-brand-100 bg-surface-elevated p-4">
              <div class="flex items-center justify-between gap-2">
                <span class="flex text-amber-500">
                  <svg v-for="n in 5" :key="n" viewBox="0 0 20 20" class="h-4 w-4" :fill="n <= r.rating ? 'currentColor' : 'none'" stroke="currentColor" stroke-width="1.2">
                    <path d="M10 1.5l2.6 5.27 5.82.85-4.21 4.1 1 5.8L10 14.9l-5.21 2.62 1-5.8-4.21-4.1 5.82-.85z" stroke-linejoin="round" />
                  </svg>
                </span>
                <span v-if="!r.is_published" class="rounded-full bg-brand-100 px-2 py-0.5 text-xs font-semibold text-brand-800">Only visible to you</span>
              </div>
              <p v-if="r.comment" class="mt-2 text-sm text-ink">{{ r.comment }}</p>
              <p v-if="r.staff_reply" class="mt-2 rounded-lg bg-brand-50 p-2.5 text-xs text-ink-muted">
                <span class="font-semibold uppercase tracking-wide text-brand-700">Owner's reply</span> — {{ r.staff_reply }}
              </p>
            </li>
          </ul>
        </section>
      </template>

      <!-- Everyone else's reviews — visible to any visitor, signed in or not -->
      <section class="mt-12 border-t border-brand-100 pt-8">
        <h2 class="text-sm font-semibold uppercase tracking-wide text-ink-subtle">What guests are saying</h2>

        <div v-if="loadingPublic" class="mt-4 space-y-3">
          <div v-for="n in 3" :key="n" class="h-20 animate-pulse rounded-2xl bg-brand-100/60" />
        </div>

        <p v-else-if="!otherReviews.length" class="mt-4 text-sm text-ink-subtle">
          {{ mine.length ? "No other reviews yet." : "No reviews yet — be the first." }}
        </p>

        <ul v-else class="mt-4 space-y-3">
          <li v-for="r in otherReviews" :key="r.id" class="rounded-2xl border border-brand-100 bg-surface-elevated p-4">
            <div class="flex items-center justify-between gap-2">
              <span class="flex text-amber-500">
                <svg v-for="n in 5" :key="n" viewBox="0 0 20 20" class="h-4 w-4" :fill="n <= r.rating ? 'currentColor' : 'none'" stroke="currentColor" stroke-width="1.2">
                  <path d="M10 1.5l2.6 5.27 5.82.85-4.21 4.1 1 5.8L10 14.9l-5.21 2.62 1-5.8-4.21-4.1 5.82-.85z" stroke-linejoin="round" />
                </svg>
              </span>
              <span class="text-xs text-ink-subtle">{{ new Date(r.created_at).toLocaleDateString() }}</span>
            </div>
            <p v-if="r.comment" class="mt-2 text-sm text-ink">{{ r.comment }}</p>
            <p class="mt-2 text-xs font-semibold uppercase tracking-wide text-ink-subtle">{{ r.reviewer_name }}</p>
            <p v-if="r.staff_reply" class="mt-2 rounded-lg bg-brand-50 p-2.5 text-xs text-ink-muted">
              <span class="font-semibold uppercase tracking-wide text-brand-700">Owner's reply</span> — {{ r.staff_reply }}
            </p>
          </li>
        </ul>

        <div v-if="pages > 1" class="mt-5 flex items-center justify-center gap-3 text-sm">
          <button type="button" class="font-medium text-brand-700 disabled:text-ink-subtle" :disabled="page <= 1" @click="page--">← Newer</button>
          <span class="text-ink-subtle">Page {{ page }} of {{ pages }}</span>
          <button type="button" class="font-medium text-brand-700 disabled:text-ink-subtle" :disabled="page >= pages" @click="page++">Older →</button>
        </div>
      </section>
    </template>
  </div>
</template>
