<script setup lang="ts">
// The platform's front page, shown on the bare domain (dineflow.io) where no single restaurant lives. Each restaurant
// has its own address (name.dineflow.io); this page explains that and is where owners sign in.
definePageMeta({ layout: 'landing' })

const config = useRuntimeConfig()
const contactEmail = config.public.contactEmail as string

useHead({
  title: 'DineFlow — online ordering, reservations and a point of sale for restaurants',
  meta: [{ name: 'description', content: 'Online ordering, table reservations, QR ordering at the table and a point of sale for restaurants, with a branded site for every restaurant.' }],
})

const features = [
  { title: 'Online ordering', body: 'Pickup, delivery and dine-in orders on your own branded site, with card payments straight to your Stripe account.' },
  { title: 'Reservations and waitlist', body: 'Guests book a table themselves; you see the floor, manage the waitlist and send reminders.' },
  { title: 'Order at the table', body: 'Guests scan a QR code, order and pay from their phone — or staff take the order on a tablet.' },
  { title: 'Kitchen screen', body: 'Tickets by station, bump when ready, mark a dish sold out and every menu updates at once.' },
  { title: 'Point of sale', body: 'An iPad till with shifts, cash and card, split bills, tips, receipts and a card reader.' },
  { title: 'Loyalty, offers and reviews', body: 'Points for regulars, discount codes, and reviews from guests who actually visited.' },
]
</script>

<template>
  <div>
    <section class="bg-[radial-gradient(ellipse_at_top_right,_var(--color-brand-100)_0%,_transparent_55%)]">
      <div class="mx-auto max-w-4xl px-4 py-20 text-center sm:px-6 sm:py-28">
        <h1 class="font-display text-4xl font-semibold leading-tight tracking-tight text-brand-900 sm:text-6xl">Everything a restaurant needs to take orders and fill tables</h1>
        <p class="mx-auto mt-6 max-w-2xl text-lg text-ink-muted">DineFlow gives every restaurant its own website for ordering and booking, plus the tools to run service: a kitchen screen, table ordering and an iPad point of sale.</p>
        <div class="mt-9 flex flex-wrap items-center justify-center gap-3">
          <NuxtLink to="/login" class="inline-flex rounded-full bg-brand-700 px-7 py-3 text-sm font-semibold text-white shadow-lg shadow-brand-900/30 hover:bg-brand-800">Restaurant sign in</NuxtLink>
          <a v-if="contactEmail" :href="`mailto:${contactEmail}`" class="inline-flex rounded-full border border-brand-200 bg-surface-elevated px-7 py-3 text-sm font-semibold text-ink hover:bg-brand-50">Get DineFlow for your restaurant</a>
        </div>
      </div>
    </section>

    <section class="mx-auto max-w-6xl px-4 py-14 sm:px-6">
      <div class="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
        <div v-for="f in features" :key="f.title" class="rounded-2xl border border-brand-100 bg-surface-elevated p-6">
          <h2 class="font-semibold text-ink">{{ f.title }}</h2>
          <p class="mt-2 text-sm leading-relaxed text-ink-muted">{{ f.body }}</p>
        </div>
      </div>
    </section>

    <section class="border-t border-brand-100 bg-surface-elevated">
      <div class="mx-auto max-w-3xl px-4 py-12 text-center sm:px-6">
        <h2 class="font-display text-2xl font-semibold text-brand-900">Looking for a restaurant?</h2>
        <p class="mt-3 text-ink-muted">Every restaurant on DineFlow has its own address, like <span class="font-medium text-ink">yourrestaurant.dineflow.io</span>. Use the link or QR code the restaurant gave you to order or book a table.</p>
      </div>
    </section>
  </div>
</template>
