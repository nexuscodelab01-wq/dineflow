/**
 * False while the server renders and during the browser's first (hydrating) render, true once the page is live.
 * Use it to gate anything that only the browser knows (who is signed in, what is in the cart) so the server and
 * the browser draw the same thing first; otherwise the browser keeps the server's markup under the wrong content.
 */
export function useHydrated() {
  const hydrated = ref(false)
  onMounted(() => { hydrated.value = true })
  return hydrated
}
