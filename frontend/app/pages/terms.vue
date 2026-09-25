<script setup lang="ts">
const branding = useBranding()
const restaurant = useRestaurantStore()
const name = computed(() => branding.name.value || restaurant.current?.name || 'this restaurant')
useHead({ title: 'Terms of service' })
</script>

<template>
  <LegalPage title="Terms of service" updated="24 September 2026">
    <p class="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-900">
      Placeholder terms for {{ name }}'s online ordering and table booking site. Written to be a
      reasonable starting point, not legal advice — have a lawyer review and adapt this before relying
      on it for a live business.
    </p>

    <h2>Using this site</h2>
    <p>
      This site lets you browse {{ name }}'s menu, order food for pickup, delivery or dine-in, and book
      a table. By placing an order or making a booking, you agree to these terms.
    </p>

    <h2>Orders</h2>
    <p>
      Prices, availability and preparation times shown here are set by {{ name }} and may change without
      notice. Placing an order is an offer to buy, which {{ name }} may accept or decline — for example
      if an item has sold out or the kitchen is closed. Payment is taken at the time of ordering.
    </p>

    <h2>Reservations</h2>
    <p>
      A table booking holds a table for the party size and time you choose, subject to {{ name }}'s
      booking policy (party size limits, lead time, and any deposit shown at the time of booking). Late
      arrival beyond the held window may result in the table being released.
    </p>

    <h2>Cancellations and refunds</h2>
    <p>
      Order and booking cancellation terms are set by {{ name }} and may be shown at checkout or in your
      confirmation email. Contact {{ name }} directly using the details on this site for any dispute
      about an order or booking.
    </p>

    <h2>Accounts</h2>
    <p>
      Keep your account password confidential. You're responsible for activity under your account. Tell
      us straight away if you think someone else has access to it.
    </p>

    <h2>Changes</h2>
    <p>These terms may be updated from time to time; the date above shows when they last changed.</p>
  </LegalPage>
</template>
