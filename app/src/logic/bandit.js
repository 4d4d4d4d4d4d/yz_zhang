// Spec 13 — multi-armed bandit (Thompson + ε-greedy), extracted from
// BanditExplorer.vue. Randomness is injected: same rng → identical run.

function thompsonSample(arm, rng) {
  // Beta(α, β) sample via mean + noise·√variance approximation.
  const mean = arm.alpha / (arm.alpha + arm.beta)
  const variance = (arm.alpha * arm.beta) /
    (Math.pow(arm.alpha + arm.beta, 2) * (arm.alpha + arm.beta + 1))
  return Math.max(0, Math.min(1, mean + (rng() - 0.5) * Math.sqrt(variance) * 4))
}

// Largest-remainder rounding so integer shares sum to exactly 100.
function shares(arms) {
  const totalAlpha = arms.reduce((s, a) => s + a.alpha, 0)
  const exact = arms.map(a => (a.alpha / totalAlpha) * 100)
  const floored = exact.map(Math.floor)
  let leftover = 100 - floored.reduce((s, v) => s + v, 0)
  const order = exact
    .map((v, i) => ({ i, frac: v - Math.floor(v) }))
    .sort((a, b) => b.frac - a.frac)
  for (const { i } of order) {
    if (leftover <= 0) break
    floored[i] += 1
    leftover -= 1
  }
  return floored
}

export function createBandit(armDefs, { epsilon = 0.15, rng = Math.random, regretWindow = 200 } = {}) {
  let eps = Math.min(1, Math.max(0, epsilon))
  let arms, cumReward, cumOptimal, regret

  function init() {
    arms = armDefs.map(d => ({ id: d.id, truth: d.truth, alpha: 1, beta: 1, pulls: 0, conv: 0 }))
    cumReward = 0
    cumOptimal = 0
    regret = []
  }
  init()

  const bestTruth = () => Math.max(...arms.map(a => a.truth))

  function step() {
    const explore = rng() < eps
    let chosen
    if (explore) {
      chosen = arms[Math.floor(rng() * arms.length)]
    } else {
      let bestS = -1
      for (const a of arms) {
        const s = thompsonSample(a, rng)
        if (s > bestS) { bestS = s; chosen = a }
      }
    }
    const reward = rng() < chosen.truth ? 1 : 0
    chosen.pulls++
    if (reward) { chosen.conv++; chosen.alpha++ } else { chosen.beta++ }
    cumReward += reward
    cumOptimal += bestTruth()
    regret.push(cumOptimal - cumReward)
    if (regret.length > regretWindow) regret.shift()
    return { armId: chosen.id, reward, explored: explore }
  }

  function snapshot() {
    const sh = shares(arms)
    return {
      arms: arms.map((a, i) => ({ ...a, share: sh[i] })),
      totalPulls: arms.reduce((s, a) => s + a.pulls, 0),
      cumReward,
      cumOptimal,
      efficiency: cumOptimal > 0 ? cumReward / cumOptimal : 0,
      regret: [...regret]
    }
  }

  return {
    step,
    snapshot,
    reset: init,
    setEpsilon(v) { eps = Math.min(1, Math.max(0, Number(v) || 0)) },
    epsilon: () => eps
  }
}
