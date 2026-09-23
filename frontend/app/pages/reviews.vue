<script setup lang="ts">
import type { EligibleVisit, Review } from '~/types/review'
import { fetchEligibleVisits, fetchMyReviews, submitReview } from '~/services/reviews'

definePageMeta({ middleware: ['auth'] })

const reviewsEnabled = useFeature('reviews')
const eligible = ref<EligibleVisit[]>([])
const mine = ref<Review[]>([])
const loading = ref(true)
const openVisit = ref<EligibleVisit | null>(null)
const rating = ref(5)
const comment = ref('')
const submitting = ref(false)
const error = ref('')

async function load() {
  const [e, r] = await Promise.all([fetchEligibleVisits(), fetchMyReviews()])
  eligible.value = e
  mine.value = r
}

onMounted(async () => {
  if (!reviewsEnabled.value) {
    loading.value = false
    return
  }
  try {
    await load()
  }
  finally {
    loading.value = false
  }
})

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
    await load()
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
    <p class="text-sm font-semibold uppercase tracking-[0.2em] text-brand-600">Your visits</p>
    <h1 class="font-display mt-2 text-3xl font-semibold text-brand-900">Reviews</h1>

    <div v-if="loading" class="mt-8 space-y-3">
      <div v-for="n in 2" :key="n" class="h-20 animate-pulse rounded-2xl bg-brand-100/60" />
    </div>

    <p v-else-if="!reviewsEnabled" class="mt-8 text-sm text-ink-subtle">Reviews aren't available here yet.</p>

    <template v-else>
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
            <span class="flex text-amber-500">
              <svg v-for="n in 5" :key="n" viewBox="0 0 20 20" class="h-4 w-4" :fill="n <= r.rating ? 'currentColor' : 'none'" stroke="currentColor" stroke-width="1.2">
                <path d="M10 1.5l2.6 5.27 5.82.85-4.21 4.1 1 5.8L10 14.9l-5.21 2.62 1-5.8-4.21-4.1 5.82-.85z" stroke-linejoin="round" />
              </svg>
            </span>
            <p v-if="r.comment" class="mt-2 text-sm text-ink">{{ r.comment }}</p>
            <p v-if="r.staff_reply" class="mt-2 rounded-lg bg-brand-50 p-2.5 text-xs text-ink-muted">
              <span class="font-semibold uppercase tracking-wide text-brand-700">Owner's reply</span> — {{ r.staff_reply }}
            </p>
          </li>
        </ul>
      </section>

      <p v-if="!eligible.length && !mine.length" class="mt-8 text-sm text-ink-subtle">
        Once you've completed an order or a booking here, you'll be able to leave a review.
      </p>
    </template>
  </div>
</template>
