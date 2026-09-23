<script setup lang="ts">
import type { AdminReview } from '~/types/review'
import { fetchAdminReviews, moderateReview, replyToReview } from '~/services/reviews'

definePageMeta({ layout: 'admin', middleware: ['staff'] })

const admin = useAdminStore()
const ui = useUiStore()

const reviews = ref<AdminReview[]>([])
const loading = ref(true)
const busyId = ref<number | null>(null)
const replyingId = ref<number | null>(null)
const replyText = ref('')
const filter = ref<'all' | 'published' | 'hidden'>('all')

async function load() {
  if (!admin.restaurantId) return
  reviews.value = await fetchAdminReviews(admin.restaurantId)
}

onMounted(async () => {
  await admin.initialize()
  await load()
  loading.value = false
})

const filtered = computed(() => {
  if (filter.value === 'published') return reviews.value.filter(r => r.is_published)
  if (filter.value === 'hidden') return reviews.value.filter(r => !r.is_published)
  return reviews.value
})

const averageRating = computed(() => {
  const published = reviews.value.filter(r => r.is_published)
  if (!published.length) return null
  return (published.reduce((sum, r) => sum + r.rating, 0) / published.length).toFixed(1)
})

async function toggle(review: AdminReview) {
  if (!admin.restaurantId || busyId.value) return
  busyId.value = review.id
  try {
    const updated = await moderateReview(admin.restaurantId, review.id, !review.is_published)
    const i = reviews.value.findIndex(r => r.id === review.id)
    if (i !== -1) reviews.value[i] = updated
  }
  catch (err) {
    ui.error(err instanceof Error ? err.message : 'Could not update this review')
  }
  finally {
    busyId.value = null
  }
}

function startReply(review: AdminReview) {
  replyingId.value = review.id
  replyText.value = review.staff_reply ?? ''
}

async function submitReply(review: AdminReview) {
  if (!admin.restaurantId || !replyText.value.trim() || busyId.value) return
  busyId.value = review.id
  try {
    const updated = await replyToReview(admin.restaurantId, review.id, replyText.value.trim())
    const i = reviews.value.findIndex(r => r.id === review.id)
    if (i !== -1) reviews.value[i] = updated
    replyingId.value = null
  }
  catch (err) {
    ui.error(err instanceof Error ? err.message : 'Could not send the reply')
  }
  finally {
    busyId.value = null
  }
}
</script>

<template>
  <div>
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="font-display text-2xl font-semibold text-brand-900">Reviews</h1>
        <p class="text-sm text-ink-muted">
          What guests are saying
          <span v-if="averageRating"> · average {{ averageRating }} / 5 ({{ reviews.filter(r => r.is_published).length }} published)</span>
        </p>
      </div>
      <div class="flex gap-1 rounded-lg border border-brand-100 bg-surface-elevated p-1 text-sm">
        <button
          v-for="opt in (['all', 'published', 'hidden'] as const)" :key="opt" type="button"
          class="rounded-md px-3 py-1 font-medium capitalize"
          :class="filter === opt ? 'bg-brand-700 text-white' : 'text-ink-muted hover:bg-brand-50'"
          @click="filter = opt"
        >
          {{ opt }}
        </button>
      </div>
    </div>

    <div v-if="loading" class="mt-6 h-40 animate-pulse rounded-2xl bg-brand-100/60" />

    <p v-else-if="!filtered.length" class="mt-8 text-sm text-ink-subtle">
      {{ reviews.length ? 'Nothing matches this filter.' : 'No reviews yet.' }}
    </p>

    <ul v-else class="mt-6 space-y-3">
      <li v-for="review in filtered" :key="review.id" class="rounded-2xl border border-brand-100 bg-surface-elevated p-4">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div class="flex items-center gap-2">
              <span class="flex text-amber-500" :aria-label="`${review.rating} out of 5 stars`">
                <svg v-for="n in 5" :key="n" viewBox="0 0 20 20" class="h-4 w-4" :fill="n <= review.rating ? 'currentColor' : 'none'" stroke="currentColor" stroke-width="1.2">
                  <path d="M10 1.5l2.6 5.27 5.82.85-4.21 4.1 1 5.8L10 14.9l-5.21 2.62 1-5.8-4.21-4.1 5.82-.85z" stroke-linejoin="round" />
                </svg>
              </span>
              <span class="font-semibold text-ink">{{ review.reviewer_name }}</span>
              <span
                v-if="!review.is_published"
                class="rounded-full bg-brand-100 px-2 py-0.5 text-xs font-semibold text-brand-800"
              >Hidden</span>
            </div>
            <p v-if="review.comment" class="mt-2 text-sm text-ink">{{ review.comment }}</p>
            <p class="mt-1 text-xs text-ink-subtle">
              {{ new Date(review.created_at).toLocaleDateString() }}
              <span v-if="review.reviewer_email"> · {{ review.reviewer_email }}</span>
            </p>
            <div v-if="review.staff_reply" class="mt-2 rounded-lg bg-brand-50 p-2.5 text-sm text-ink">
              <p class="text-xs font-semibold uppercase tracking-wide text-brand-700">Your reply</p>
              <p class="mt-0.5">{{ review.staff_reply }}</p>
            </div>
          </div>
          <div class="flex shrink-0 flex-wrap items-center gap-2">
            <button
              type="button" class="rounded-lg border border-brand-200 px-3 py-1.5 text-sm font-medium hover:bg-brand-50"
              :disabled="busyId === review.id" @click="toggle(review)"
            >
              {{ review.is_published ? 'Hide' : 'Publish' }}
            </button>
            <button
              type="button" class="rounded-lg border border-brand-200 px-3 py-1.5 text-sm font-medium hover:bg-brand-50"
              :disabled="busyId === review.id" @click="startReply(review)"
            >
              {{ review.staff_reply ? 'Edit reply' : 'Reply' }}
            </button>
          </div>
        </div>

        <div v-if="replyingId === review.id" class="mt-3 flex flex-wrap items-start gap-2 border-t border-brand-100 pt-3">
          <textarea
            v-model="replyText" rows="2" maxlength="2000" placeholder="Thanks for the kind words…"
            class="min-w-[16rem] flex-1 rounded-lg border px-3 py-2 text-sm"
          />
          <div class="flex flex-col gap-2">
            <button
              type="button" class="rounded-lg bg-brand-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-800"
              :disabled="!replyText.trim() || busyId === review.id" @click="submitReply(review)"
            >
              Send
            </button>
            <button type="button" class="text-sm text-ink-subtle hover:underline" @click="replyingId = null">Cancel</button>
          </div>
        </div>
      </li>
    </ul>
  </div>
</template>
