/** A short two-tone "ding" for a new ticket, made with the browser's audio (no sound file to ship). */

let context: AudioContext | null = null

function audio(): AudioContext | null {
  if (typeof window === 'undefined') return null
  const Ctx = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
  if (!Ctx) return null
  context ??= new Ctx()
  return context
}

/** Browsers only allow sound after a tap; call this from a click handler (e.g. the sound toggle). */
export function unlockSound(): boolean {
  const ctx = audio()
  if (!ctx) return false
  void ctx.resume()
  return true
}

export function playDing(): void {
  const ctx = audio()
  if (!ctx || ctx.state !== 'running') return // still locked: better silent than an error
  const now = ctx.currentTime
  ;[880, 1320].forEach((frequency, i) => {
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    osc.type = 'sine'
    osc.frequency.value = frequency
    gain.gain.setValueAtTime(0.0001, now + i * 0.18)
    gain.gain.exponentialRampToValueAtTime(0.3, now + i * 0.18 + 0.02)
    gain.gain.exponentialRampToValueAtTime(0.0001, now + i * 0.18 + 0.4)
    osc.connect(gain).connect(ctx.destination)
    osc.start(now + i * 0.18)
    osc.stop(now + i * 0.18 + 0.45)
  })
}
