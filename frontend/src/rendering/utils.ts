export function smoothstep(t: number): number {
  const tt = Math.max(0, Math.min(1, t))
  return tt * tt * (3 - 2 * tt)
}

export function randRange(min: number, max: number): number {
  return min + Math.random() * (max - min)
}

export function randChoice<T>(arr: T[]): T {
  return arr[Math.floor(Math.random() * arr.length)]!
}

export function weightedChoice<T>(items: T[], weights: number[]): T {
  const total = weights.reduce((a, b) => a + b, 0)
  let r = Math.random() * total
  for (let i = 0; i < items.length; i++) {
    r -= weights[i]!
    if (r <= 0) return items[i]!
  }
  return items[items.length - 1]!
}

