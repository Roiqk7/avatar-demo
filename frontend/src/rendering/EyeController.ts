import { BLINK_POOL, GOOFY_POOL, type EyeSeqStep } from './eyeSequences'
import { randChoice, randRange, smoothstep, weightedChoice } from './utils'

export type EyeConfig = {
  enable_micro_glance: boolean
  enable_long_glance: boolean
  enable_expr_glance: boolean
  enable_goofy_sequences: boolean
  blink_initial_ms: [number, number]
  blink_after_ms: [number, number]
  micro_initial_ms: [number, number]
  micro_after_ms: [number, number]
  micro_glance_indices: number[]
  micro_return_ms: [number, number]
  glance_initial_ms: [number, number]
  glance_after_ms: [number, number]
  glance_indices: number[]
  glance_return_ms: [number, number]
  expr_initial_ms: [number, number]
  expr_after_ms: [number, number]
  expr_indices: number[]
  expr_return_ms: [number, number]
  goofy_initial_ms: [number, number]
  goofy_after_ms: [number, number]
  micro_transition_ms: number
  glance_transition_ms: number
  expr_transition_ms: number
  forbidden_eye_indices: number[]
}

function eyeSeqUsesForbidden(seq: EyeSeqStep[], forbidden: Set<number>): boolean {
  if (!forbidden || forbidden.size === 0) return false
  return seq.some(([idx]) => forbidden.has(idx))
}

export class EyeController {
  cfg: EyeConfig
  forbiddenEyeIndices: Set<number>

  _current = 0
  _prev = 0
  _transStart = 0
  _transDur = 0
  _inTrans = false

  _seq: EyeSeqStep[] = []
  _seqStep = 0
  _seqStepStart = 0
  _seqActive = false

  _lookReturnMs = 0
  _lookingAway = false

  _nextBlinkMs: number
  _nextMicroMs: number
  _nextGlanceMs: number
  _nextExprMs: number
  _nextGoofyMs: number

  constructor(cfg: EyeConfig) {
    this.cfg = cfg
    this.forbiddenEyeIndices = new Set(cfg.forbidden_eye_indices || [])

    this._nextBlinkMs = randRange(cfg.blink_initial_ms[0], cfg.blink_initial_ms[1])
    this._nextMicroMs = cfg.enable_micro_glance ? randRange(cfg.micro_initial_ms[0], cfg.micro_initial_ms[1]) : Infinity
    this._nextGlanceMs = cfg.enable_long_glance ? randRange(cfg.glance_initial_ms[0], cfg.glance_initial_ms[1]) : Infinity
    this._nextExprMs = cfg.enable_expr_glance ? randRange(cfg.expr_initial_ms[0], cfg.expr_initial_ms[1]) : Infinity
    this._nextGoofyMs = cfg.enable_goofy_sequences ? randRange(cfg.goofy_initial_ms[0], cfg.goofy_initial_ms[1]) : Infinity
  }

  transitionTo(idx: number, durMs: number, elapsedMs: number) {
    if (idx === this._current && !this._inTrans) return
    this._prev = this._visible(elapsedMs)
    this._current = idx
    this._transStart = elapsedMs
    this._transDur = durMs
    this._inTrans = true
  }

  _visible(elapsedMs: number): number {
    return this._t(elapsedMs) >= 0.5 ? this._current : this._prev
  }

  _t(elapsedMs: number): number {
    if (!this._inTrans) return 1
    const raw = (elapsedMs - this._transStart) / Math.max(1, this._transDur)
    const t = smoothstep(Math.min(1, raw))
    if (t >= 1) this._inTrans = false
    return t
  }

  playSequence(seq: EyeSeqStep[], elapsedMs: number) {
    this._seq = seq
    this._seqStep = 0
    this._seqStepStart = elapsedMs
    this._seqActive = true
    this._lookingAway = false
    const [idx, transMs] = seq[0]!
    this.transitionTo(idx, transMs, elapsedMs)
  }

  _advanceSeq(elapsedMs: number) {
    if (!this._seqActive) return
    const [, transMs, holdMs] = this._seq[this._seqStep]!
    if (elapsedMs - this._seqStepStart >= transMs + holdMs) {
      this._seqStep++
      if (this._seqStep >= this._seq.length) {
        this._seqActive = false
        return
      }
      const [nidx, ntrans] = this._seq[this._seqStep]!
      this.transitionTo(nidx, ntrans, elapsedMs)
      this._seqStepStart = elapsedMs
    }
  }

  getBlend(elapsedMs: number): { fromIdx: number; toIdx: number; t: number } {
    const cfg = this.cfg

    if (this._seqActive) {
      this._advanceSeq(elapsedMs)
    } else if (this._lookingAway && elapsedMs >= this._lookReturnMs) {
      this._lookingAway = false
      this.transitionTo(0, 264, elapsedMs)
    } else if (!this._seqActive && !this._lookingAway) {
      if (elapsedMs >= this._nextBlinkMs) {
        const seq = weightedChoice(
          BLINK_POOL.map((b) => b.seq),
          BLINK_POOL.map((b) => b.weight),
        )
        this.playSequence(seq, elapsedMs)
        this._nextBlinkMs = elapsedMs + randRange(cfg.blink_after_ms[0], cfg.blink_after_ms[1])
      } else if (cfg.enable_micro_glance && cfg.micro_glance_indices.length && elapsedMs >= this._nextMicroMs) {
        this.transitionTo(randChoice(cfg.micro_glance_indices), cfg.micro_transition_ms, elapsedMs)
        this._lookingAway = true
        this._lookReturnMs = elapsedMs + randRange(cfg.micro_return_ms[0], cfg.micro_return_ms[1])
        this._nextMicroMs = elapsedMs + randRange(cfg.micro_after_ms[0], cfg.micro_after_ms[1])
      } else if (cfg.enable_long_glance && cfg.glance_indices.length && elapsedMs >= this._nextGlanceMs) {
        this.transitionTo(randChoice(cfg.glance_indices), cfg.glance_transition_ms, elapsedMs)
        this._lookingAway = true
        this._lookReturnMs = elapsedMs + randRange(cfg.glance_return_ms[0], cfg.glance_return_ms[1])
        this._nextGlanceMs = elapsedMs + randRange(cfg.glance_after_ms[0], cfg.glance_after_ms[1])
      } else if (cfg.enable_expr_glance && cfg.expr_indices.length && elapsedMs >= this._nextExprMs) {
        this.transitionTo(randChoice(cfg.expr_indices), cfg.expr_transition_ms, elapsedMs)
        this._lookingAway = true
        this._lookReturnMs = elapsedMs + randRange(cfg.expr_return_ms[0], cfg.expr_return_ms[1])
        this._nextExprMs = elapsedMs + randRange(cfg.expr_after_ms[0], cfg.expr_after_ms[1])
      } else if (cfg.enable_goofy_sequences && elapsedMs >= this._nextGoofyMs) {
        const ok = GOOFY_POOL.filter((s) => !eyeSeqUsesForbidden(s, this.forbiddenEyeIndices))
        if (ok.length) this.playSequence(randChoice(ok), elapsedMs)
        this._nextGoofyMs = elapsedMs + randRange(cfg.goofy_after_ms[0], cfg.goofy_after_ms[1])
      }
    }

    const t = this._t(elapsedMs)
    return { fromIdx: this._prev, toIdx: this._current, t }
  }

  get stateLabel(): 'seq' | 'look' | 'idle' {
    if (this._seqActive) return 'seq'
    if (this._lookingAway) return 'look'
    return 'idle'
  }
}

