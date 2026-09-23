/**
 * `v-reveal`: fades an element up into view the first time it scrolls into the viewport — a light
 * touch of motion for marketing-style pages (the home page). Elements start invisible via the
 * `reveal-pending` class (see main.css) so there's no flash before hydration; this plugin removes
 * it and adds the animation class once, then stops observing.
 *
 * Respects prefers-reduced-motion by revealing everything immediately, no animation, no observer.
 */
export default defineNuxtPlugin((nuxtApp) => {
  const reduceMotion = typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches

  let observer: IntersectionObserver | null = null
  if (!reduceMotion && typeof IntersectionObserver !== 'undefined') {
    observer = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) {
          entry.target.classList.remove('reveal-pending')
          entry.target.classList.add('animate-fade-up')
          observer!.unobserve(entry.target)
        }
      }
    }, { threshold: 0.15, rootMargin: '0px 0px -40px 0px' })
  }

  nuxtApp.vueApp.directive('reveal', {
    mounted(el: HTMLElement) {
      if (reduceMotion || !observer) {
        el.classList.remove('reveal-pending')
        return
      }
      el.classList.add('reveal-pending')
      observer.observe(el)
    },
    unmounted(el: HTMLElement) {
      observer?.unobserve(el)
    },
  })
})
