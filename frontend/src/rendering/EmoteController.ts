import type { EyeController } from './EyeController'
import type { MouthController } from './MouthController'
import { randChoice, randRange } from './utils'

export type Emote = {
  name: string
  eye_seq: Array<[number, number, number]>
  mouth: string
  mouth_hold_ms: number
}

export type EmoteTiming = {
  enabled: boolean
  idle_delay_ms: number
  first_emote_after_ms: [number, number]
  emote_after_ms: [number, number]
}

function eyeSeqUsesForbidden(seq: Array<[number, number, number]>, forbidden: Set<number>): boolean {
  if (!forbidden || forbidden.size === 0) return false
  return seq.some(([idx]) => forbidden.has(idx))
}

export class EmoteController {
  _emotes: Emote[]
  _timing: EmoteTiming
  _idle = false
  _idleSinceMs = 0
  _nextEmoteMs = 0
  _active = false
  _emote: Emote | null = null
  _startMs = 0

  constructor(emotes: Emote[], timing: EmoteTiming) {
    this._emotes = emotes
    this._timing = timing
  }

  notifySpeaking() {
    this._idle = false
    this._active = false
    this._emote = null
  }

  notifyIdle(nowMs: number) {
    if (!this._timing.enabled || !this._emotes.length) return
    if (!this._idle) {
      this._idle = true
      this._idleSinceMs = nowMs
      this._nextEmoteMs =
        nowMs + this._timing.idle_delay_ms + randRange(this._timing.first_emote_after_ms[0], this._timing.first_emote_after_ms[1])
    }
  }

  update(
    elapsedMs: number,
    eyeCtrl: EyeController,
    mouthCtrl: MouthController,
    availableMouthNames: Set<string>,
  ): boolean {
    if (!this._timing.enabled || !this._emotes.length) return false
    if (!this._idle) return false
    if (elapsedMs - this._idleSinceMs < this._timing.idle_delay_ms) return false

    if (this._active && this._emote) {
      const totalEyeMs = this._emote.eye_seq.reduce((s, [, t, h]) => s + t + h, 0)
      const emoteDur = Math.max(totalEyeMs, this._emote.mouth_hold_ms)
      if (elapsedMs - this._startMs > emoteDur) {
        this._active = false
        this._emote = null
        eyeCtrl.transitionTo(0, 250, elapsedMs)
        mouthCtrl.transitionTo(null, 350, elapsedMs)
        this._nextEmoteMs = elapsedMs + randRange(this._timing.emote_after_ms[0], this._timing.emote_after_ms[1])
        return false
      }
      return true
    }

    if (elapsedMs >= this._nextEmoteMs) {
      const forbidden = eyeCtrl.forbiddenEyeIndices
      const pool = this._emotes.filter((e) => availableMouthNames.has(e.mouth) && !eyeSeqUsesForbidden(e.eye_seq, forbidden))
      if (pool.length) {
        const emote = randChoice(pool)
        this._emote = emote
        this._active = true
        this._startMs = elapsedMs
        eyeCtrl.playSequence(emote.eye_seq, elapsedMs)
        mouthCtrl.beginHold(emote.mouth, 300, emote.mouth_hold_ms, elapsedMs)
        return true
      }
      this._nextEmoteMs = elapsedMs + randRange(this._timing.emote_after_ms[0], this._timing.emote_after_ms[1])
    }

    return false
  }
}

