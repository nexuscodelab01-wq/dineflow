<script setup lang="ts">
const branding = useBranding()
const restaurant = useRestaurantStore()
const name = computed(() => branding.name.value || restaurant.current?.name || 'this restaurant')
useHead({ title: 'Cookie policy' })
</script>

<template>
  <LegalPage title="Cookie policy" updated="24 September 2026">
    <p class="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-900">
      Placeholder cookie policy for {{ name }}'s online ordering and table booking site — not legal
      advice. Kept accurate to how this site actually works: it does not use tracking or advertising
      cookies at all.
    </p>

    <h2>No tracking cookies</h2>
    <p>
      This site does not use advertising or analytics cookies, and does not track you across other
      websites. There is nothing here to opt out of on that front.
    </p>

    <h2>What is stored in your browser</h2>
    <p>Instead of cookies, this site uses your browser's local storage for a few things, only on this site's own address:</p>
    <ul>
      <li><strong>Signed-in session</strong> — if you create an account, a token that keeps you signed in.</li>
      <li><strong>Cart</strong> — the items you've added, so they survive a page reload.</li>
      <li><strong>Table pass</strong> — if you order from a table via QR code, a pass that identifies your device at that table (not a login).</li>
      <li><strong>Small preferences</strong> — things like a remembered tab or a dismissed banner.</li>
    </ul>
    <p>
      None of this is shared with other websites — it lives only in your browser, only for this site.
      Clearing your browser's site data removes all of it, including anything in your cart.
    </p>

    <h2>Essential to the site working</h2>
    <p>
      All of the above is necessary for ordering, booking and staying signed in to work — there's no
      separate consent banner because there's nothing non-essential being stored.
    </p>
  </LegalPage>
</template>
