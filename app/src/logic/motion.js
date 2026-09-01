// Spec 38 — reduced-motion resolution. Pure: combines the OS
// `prefers-reduced-motion` signal with an explicit user preference. The user
// choice wins over the OS so someone can force motion on/off regardless of
// their system setting (GitHub/Slack do the same).

export const MOTION_PREFS = ['system', 'reduce', 'full']

// osReduce: boolean from matchMedia. userPref: one of MOTION_PREFS.
// Returns true when animation should be suppressed.
export function resolveMotion(osReduce, userPref = 'system') {
  if (userPref === 'reduce') return true
  if (userPref === 'full') return false
  return Boolean(osReduce) // 'system' (or anything unknown) follows the OS
}

// Cycle order for a single toggle control: system → reduce → full → system.
export function nextMotionPref(pref) {
  // indexOf → -1 for unknown; (i + 1) % len then wraps to 0 ('system'),
  // so the result is always a valid pref.
  const i = MOTION_PREFS.indexOf(pref)
  return MOTION_PREFS[(i + 1) % MOTION_PREFS.length]
}
