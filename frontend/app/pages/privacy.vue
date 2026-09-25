<script setup lang="ts">
const branding = useBranding()
const restaurant = useRestaurantStore()
const name = computed(() => branding.name.value || restaurant.current?.name || 'this restaurant')
const email = computed(() => restaurant.current?.email)
useHead({ title: 'Privacy policy' })
</script>

<template>
  <LegalPage title="Privacy policy" updated="24 September 2026">
    <p class="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-900">
      Placeholder privacy policy for {{ name }}'s online ordering and table booking site. Written to be
      a reasonable starting point, not legal advice — have a lawyer review this, particularly for
      GDPR/UK-GDPR compliance, before relying on it for a live business.
    </p>

    <h2>What we collect</h2>
    <p>
      When you order, book a table, or create an account, {{ name }} collects your name, email address,
      phone number, and — for delivery — your address. Order and booking history is kept so you (and
      {{ name }}'s staff) can see past visits.
    </p>

    <h2>How it's used</h2>
    <ul>
      <li>To take and prepare your order or booking, and to contact you about it.</li>
      <li>To send confirmation, reminder and receipt emails.</li>
      <li>To let {{ name }}'s staff see your order/booking history if you're a returning guest.</li>
      <li>If you opt in to a loyalty or rewards feature, to track and show your points balance.</li>
    </ul>

    <h2>What we don't do</h2>
    <p>
      Your details are not sold. They're used by {{ name }} to run this site, not shared with other
      restaurants or third parties beyond what's needed to deliver the service (for example, sending
      email, or processing a card payment).
    </p>

    <h2>Your choices</h2>
    <p>
      You can ask to see, correct or delete your data, or ask us to stop using it, by contacting
      {{ name }} <span v-if="email">at <a :href="`mailto:${email}`">{{ email }}</a></span><span v-else>using the contact details on this site</span>.
    </p>

    <h2>Cookies</h2>
    <p>See our <NuxtLink to="/cookies">cookie policy</NuxtLink> for what's stored in your browser and why.</p>
  </LegalPage>
</template>
