import { randChoice, randRange, smoothstep } from './utils'

export type MouthPools = {
  subtle: string[]
  happy: string[]
  goofy: string[]
  dramatic: string[]
}

export type MouthTiming = {
  idle_delay_ms: number
  subtle_next_initial: [number, number]
  subtle_next_after: [number, number]
  happy_next_initial: [number, number]
  happy_next_after: [number, number]
  goofy_next_initial: [number, number]
  goofy_next_after: [number, number]
  dramatic_next_initial: [number, number]
  dramatic_next_after: [number, number]
  subtle_transition_ms: number
  subtle_hold_ms: [number, number]
  happy_transition_ms: number
  happy_hold_ms: [number, number]
  goofy_transition_ms: number
  goofy_hold_ms: [number, number]
  dramatic_transition_ms: number
  dramatic_hold_ms: [number, number]
  return_transition_ms: number
}

export class MouthController {
  _pools: MouthPools
  _timing: MouthTiming
  _idleAnimEnabled: boolean

  _current: string | null = null
  _prev: string | null = null
  _transStart = 0
  _transDur = 0
  _inTrans = false
  _idleSinceMs = 0
  _idle = false
  _returnMs = 0
  _holding = false
  _nextSubtleMs = 0
  _nextHappyMs = 0
  _nextGoofyMs = 0
  _nextDramaticMs = 0

  constructor(pools: MouthPools, timing: MouthTiming, idleAnimEnabled = true) {
    this._pools = pools
    this._timing = timing
    this._idleAnimEnabled = idleAnimEnabled
    this._resetTimers(0)
  }

  _resetTimers(now: number) {
    const t = this._timing
    this._nextSubtleMs = now + randRange(t.subtle_next_initial[0], t.subtle_next_initial[1])
    this._nextHappyMs = now + randRange(t.happy_next_initial[0], t.happy_next_initial[1])
    this._nextGoofyMs = now + randRange(t.goofy_next_initial[0], t.goofy_next_initial[1])
    this._nextDramaticMs = now + randRange(t.dramatic_next_initial[0], t.dramatic_next_initial[1])
  }

  transitionTo(name: string | null, durMs: number, elapsedMs: number) {
    const vis = this._visible(elapsedMs)
    if (name === vis) return
    this._prev = vis
    this._current = name
    this._transStart = elapsedMs
    this._transDur = durMs
    this._inTrans = true
  }

  _visible(elapsedMs: number): string | null {
    return this._t(elapsedMs) >= 0.5 ? this._current : this._prev
  }

  _t(elapsedMs: number): number {
    if (!this._inTrans) return 1
    const raw = (elapsedMs - this._transStart) / Math.max(1, this._transDur)
    const t = smoothstep(Math.min(1, raw))
    if (t >= 1) this._inTrans = false
    return t
  }

  notifySpeaking() {
    this._idle = false
    this._current = null
    this._prev = null
    this._inTrans = false
    this._holding = false
  }

  notifyIdle(nowMs: number) {
    if (!this._idle) {
      this._idle = true
      this._idleSinceMs = nowMs
      this._resetTimers(nowMs + this._timing.idle_delay_ms)
    }
  }

  beginHold(name: string | null, transMs: number, holdMs: number, elapsedMs: number) {
    this.transitionTo(name, transMs, elapsedMs)
    this._holding = true
    this._returnMs = elapsedMs + holdMs
  }

  getIdleMouth(
    elapsedMs: number,
    availableNames: Set<string>,
  ): { prev: string | null; cur: string | null; t: number } {
    if (!this._idle) return { prev: null, cur: null, t: 1 }
    if (!this._idleAnimEnabled) return { prev: null, cur: null, t: 1 }
    if (elapsedMs - this._idleSinceMs < this._timing.idle_delay_ms) return { prev: null, cur: null, t: 1 }

    if (this._holding && elapsedMs >= this._returnMs) {
      this._holding = false
      this.transitionTo(null, this._timing.return_transition_ms, elapsedMs)
    }

    const tc = this._timing
    const pools = this._pools

    if (!this._holding && !this._inTrans) {
      const tryTier = (
        timerProp: '_nextSubtleMs' | '_nextHappyMs' | '_nextGoofyMs' | '_nextDramaticMs',
        nextAfter: [number, number],
        poolNames: string[],
        tranMs: number,
        holdRange: [number, number],
      ) => {
        if (elapsedMs >= this[timerProp]) {
          const avail = poolNames.filter((n) => availableNames.has(n))
          if (avail.length) {
            this.beginHold(randChoice(avail), tranMs, randRange(holdRange[0], holdRange[1]), elapsedMs)
          }
          this[timerProp] = elapsedMs + randRange(nextAfter[0], nextAfter[1])
          return true
        }
        return false
      }

      tryTier('_nextSubtleMs', tc.subtle_next_after, pools.subtle, tc.subtle_transition_ms, tc.subtle_hold_ms) ||
        tryTier('_nextHappyMs', tc.happy_next_after, pools.happy, tc.happy_transition_ms, tc.happy_hold_ms) ||
        tryTier('_nextGoofyMs', tc.goofy_next_after, pools.goofy, tc.goofy_transition_ms, tc.goofy_hold_ms) ||
        tryTier('_nextDramaticMs', tc.dramatic_next_after, pools.dramatic, tc.dramatic_transition_ms, tc.dramatic_hold_ms)
    }

    const t = this._t(elapsedMs)
    return { prev: this._prev, cur: this._current, t }
  }
}

