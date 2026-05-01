import * as React from 'react'
import { isSafari as IS_SAFARI } from '../utils/browser'

type VadCallbacks = {
  onSpeechStart?: () => void
  onSpeechEnd?: () => void
  onSilenceCommit?: () => void
}

const SILENCE_COMMIT_MS = 900
const COMMIT_GRACE_MS = 150
const BASELINE_SMOOTHING = 0.02
const SPEECH_ON_MULT = 2.6
const SPEECH_OFF_MULT = 1.7
const MIN_SPEECH_MS = 120
const CONFIRM_SPEECH_MS = 160
const MIN_LEVEL_FOR_CONFIRM_MULT = 1.15
const ABS_ON_FLOOR = 0.008
const ABS_OFF_FLOOR = 0.006

type ControlRefs = {
  rafId: number | null
  baseline: number
  speechActive: boolean
  speechStartMs: number | null
  speechConfirmMs: number | null
  speechConfirmed: boolean
  lastVoiceMs: number | null
  pendingCommitSinceMs: number | null
  emittedStart: boolean
}

function rms(samples: Float32Array): number {
  let sum = 0
  for (let i = 0; i < samples.length; i++) {
    const v = samples[i] ?? 0
    sum += v * v
  }
  return Math.sqrt(sum / Math.max(1, samples.length))
}

function clamp01(x: number): number {
  return Math.max(0, Math.min(1, x))
}

/**
 * Runs an RMS-based voice activity detector against a live AnalyserNode.
 * Emits speech-start (after CONFIRM_SPEECH_MS of confirmed speech),
 * speech-end (immediate on transition), and silence-commit (after SILENCE_COMMIT_MS quiet).
 */
export function useMicVad(callbacks: VadCallbacks): {
  start: (analyser: AnalyserNode) => void
  stop: () => void
} {
  const refs = React.useRef<ControlRefs>(initialRefs())
  const cbRef = React.useRef(callbacks)
  React.useLayoutEffect(() => {
    cbRef.current = callbacks
  })

  const stop = React.useCallback(() => {
    if (refs.current.rafId !== null) cancelAnimationFrame(refs.current.rafId)
    refs.current = initialRefs()
  }, [])

  const start = React.useCallback(
    (analyser: AnalyserNode) => {
      stop()
      const timeDomain = new Float32Array(analyser.fftSize)
      const step = () => {
        refs.current.rafId = requestAnimationFrame(step)
        analyser.getFloatTimeDomainData(timeDomain)
        const level = rms(timeDomain)
        tickVad(level, refs.current, cbRef.current)
      }
      refs.current.rafId = requestAnimationFrame(step)
    },
    [stop],
  )

  React.useEffect(() => () => stop(), [stop])

  return { start, stop }
}

function initialRefs(): ControlRefs {
  return {
    rafId: null,
    baseline: 0.012,
    speechActive: false,
    speechStartMs: null,
    speechConfirmMs: null,
    speechConfirmed: false,
    lastVoiceMs: null,
    pendingCommitSinceMs: null,
    emittedStart: false,
  }
}

function tickVad(level: number, r: ControlRefs, cb: VadCallbacks): void {
  // Adapt baseline slowly; bias toward updating only during quiet stretches.
  const quietBias = clamp01((r.baseline * 1.5 - level) / Math.max(1e-6, r.baseline))
  const alpha = BASELINE_SMOOTHING * (0.2 + 0.8 * quietBias)
  r.baseline = r.baseline * (1 - alpha) + level * alpha

  const now = performance.now()
  const onMult = IS_SAFARI ? 2.0 : SPEECH_ON_MULT
  const offMult = IS_SAFARI ? 1.4 : SPEECH_OFF_MULT
  const absOn = IS_SAFARI ? 0.004 : ABS_ON_FLOOR
  const absOff = IS_SAFARI ? 0.003 : ABS_OFF_FLOOR
  const onThresh = Math.max(absOn, r.baseline * onMult)
  const offThresh = Math.max(absOff, r.baseline * offMult)
  const isSpeechNow = r.speechActive ? level >= offThresh : level >= onThresh

  if (isSpeechNow) {
    handleSpeechFrame(r, cb, now, level, onThresh)
    return
  }
  if (!r.speechActive) return
  handleSilenceFrame(r, cb, now)
}

function handleSpeechFrame(r: ControlRefs, cb: VadCallbacks, now: number, level: number, onThresh: number): void {
  r.lastVoiceMs = now
  r.pendingCommitSinceMs = null
  if (!r.speechActive) {
    r.speechActive = true
    r.speechStartMs = now
    r.speechConfirmMs = now
    r.speechConfirmed = false
  }
  const confirmAt = r.speechConfirmMs ?? now
  const confirmedFor = now - confirmAt
  const aboveConfirmLevel = level >= onThresh * MIN_LEVEL_FOR_CONFIRM_MULT
  if (!r.speechConfirmed && confirmedFor >= CONFIRM_SPEECH_MS && aboveConfirmLevel) {
    r.speechConfirmed = true
    r.emittedStart = true
    cb.onSpeechStart?.()
  }
}

function handleSilenceFrame(r: ControlRefs, cb: VadCallbacks, now: number): void {
  const speechStart = r.speechStartMs ?? now
  const lastVoice = r.lastVoiceMs ?? speechStart
  const spokeFor = now - speechStart
  const silentFor = now - lastVoice

  if (!r.speechConfirmed) {
    if (spokeFor < MIN_SPEECH_MS && silentFor > 250) {
      resetSpeechRefs(r)
      return
    }
    if (silentFor > 220) {
      resetSpeechRefs(r)
    }
    return
  }

  if (silentFor < SILENCE_COMMIT_MS) {
    r.pendingCommitSinceMs = null
    return
  }
  if (r.pendingCommitSinceMs === null) {
    r.pendingCommitSinceMs = now
    return
  }
  if (now - r.pendingCommitSinceMs < COMMIT_GRACE_MS) return

  if (r.emittedStart) cb.onSpeechEnd?.()
  cb.onSilenceCommit?.()
  resetSpeechRefs(r)
}

function resetSpeechRefs(r: ControlRefs): void {
  r.speechActive = false
  r.speechStartMs = null
  r.speechConfirmMs = null
  r.speechConfirmed = false
  r.lastVoiceMs = null
  r.pendingCommitSinceMs = null
  r.emittedStart = false
}
