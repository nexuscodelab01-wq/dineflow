<script setup lang="ts">
import { formatCurrency } from '~/utils/format'
import { resolveMediaUrl, thumbnailUrl } from '~/utils/media'

const props = defineProps<{
  name: string
  description?: string | null
  price: string
  imageUrl?: string | null
  categoryName?: string | null
  isVegetarian?: boolean
  isSpicy?: boolean
  isPopular?: boolean
  unavailable?: boolean
}>()

defineEmits<{ click: [] }>()

// Cards are small: load the thumbnail, and fall back to the full image if it is missing.
const thumbFailed = ref(false)
const resolvedImage = computed(() =>
  resolveMediaUrl(thumbFailed.value ? props.imageUrl : thumbnailUrl(props.imageUrl)),
)
</script>

<template>
  <article
    class="group flex cursor-pointer flex-col overflow-hidden rounded-2xl border border-brand-100 bg-surface-elevated transition hover:border-brand-300 hover:shadow-md"
    :class="{ 'opacity-60': unavailable }"
    @click="$emit('click')"
  >
    <div class="relative aspect-[4/3] overflow-hidden bg-gradient-to-br from-brand-50 to-brand-100">
      <img
        v-if="resolvedImage"
        :src="resolvedImage"
        :alt="name"
        class="h-full w-full object-cover transition duration-300 group-hover:scale-105"
        loading="lazy"
        @error="thumbFailed = true"
      >
      <span v-else class="flex h-full items-center justify-center font-display text-3xl text-brand-700/40">
        {{ name.charAt(0) }}
      </span>
    </div>
    <div class="flex flex-1 flex-col p-4">
      <div class="mb-2 flex flex-wrap gap-1.5">
        <span v-if="isPopular" class="rounded-full bg-brand-100 px-2 py-0.5 text-xs font-medium text-brand-800">Popular</span>
        <span v-if="isVegetarian" class="rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-800">Vegetarian</span>
        <span v-if="isSpicy" class="rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-800">Spicy</span>
        <span v-if="unavailable" class="rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-600">Unavailable</span>
      </div>
      <h3 class="font-semibold text-ink group-hover:text-brand-800">
        {{ name }}
      </h3>
      <p v-if="categoryName" class="mt-0.5 text-xs text-ink-subtle">
        {{ categoryName }}
      </p>
      <p v-if="description" class="mt-2 line-clamp-2 text-sm text-ink-muted">
        {{ description }}
      </p>
      <p class="mt-auto pt-3 text-lg font-semibold text-brand-800">
        {{ formatCurrency(Number(price)) }}
      </p>
    </div>
  </article>
</template>
