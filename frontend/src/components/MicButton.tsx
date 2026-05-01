import * as React from 'react'

function getMimeType(): string {
  const types = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/ogg', 'audio/wav']
  for (const t of types) {
    if (typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported(t)) return t
  }
  return ''
}

function clamp01(x: number): number {
  return Math.max(0, Math.min(1, x))
}

function rms(samples: Float32Array): number {
  let sum = 0
  for (let i = 0; i < samples.length; i++) {
    const v = samples[i] ?? 0
    sum += v * v
  }
  return Math.sqrt(sum / Math.max(1, samples.length))
}

type MicStatus = { text: string; className?: string }

export function MicButton(props: {
  disabled?: boolean
  onRecorded: (blob: Blob, mimeType: string) => Promise<void> | void
  onHint?: (hint: string) => void
  onStatus?: (status: MicStatus) => void
  onUserGesture?: () => void
  onSpeechStart?: () => void
  onStopInterrupt?: () => void
  onListeningChange?: (isListening: boolean) => void
  onAudioFrame?: (samples: Float32Array) => void
}) {
  const { disabled, onRecorded, onHint, onStatus, onUserGesture, onSpeechStart, onStopInterrupt, onListeningChange, onAudioFrame } = props

  const onRecordedRef = React.useRef(onRecorded)
  const onHintRef = React.useRef(onHint)
  const onStatusRef = React.useRef(onStatus)
  const onSpeechStartRef = React.useRef(onSpeechStart)
  const onStopInterruptRef = React.useRef(onStopInterrupt)
  const onListeningChangeRef = React.useRef(onListeningChange)
  const onAudioFrameRef = React.useRef(onAudioFrame)
  React.useLayoutEffect(() => {
    onRecordedRef.current = onRecorded
    onHintRef.current = onHint
    onStatusRef.current = onStatus
    onSpeechStartRef.current = onSpeechStart
    onStopInterruptRef.current = onStopInterrupt
    onListeningChangeRef.current = onListeningChange
    onAudioFrameRef.current = onAudioFrame
  })

  const [isListening, setIsListening] = React.useState(false)
  const [isSubmitting, setIsSubmitting] = React.useState(false)
  const isSubmittingRef = React.useRef(false)

  const mediaRecorderRef = React.useRef<MediaRecorder | null>(null)
  const streamRef = React.useRef<MediaStream | null>(null)
  const chunksRef = React.useRef<Blob[]>([])

  const audioCtxRef = React.useRef<AudioContext | null>(null)
  const analyserRef = React.useRef<AnalyserNode | null>(null)
  const vadRafRef = React.useRef<number | null>(null)

  const speechActiveRef = React.useRef(false)
  const speechStartMsRef = React.useRef<number | null>(null)
  const speechConfirmMsRef = React.useRef<number | null>(null)
  const speechConfirmedRef = React.useRef(false)
  const lastVoiceMsRef = React.useRef<number | null>(null)
  const baselineRef = React.useRef<number>(0.012)
  const pendingCommitSinceMsRef = React.useRef<number | null>(null)

  React.useEffect(() => {
    isSubmittingRef.current = isSubmitting
  }, [isSubmitting])

  const stopAll = React.useCallback((opts?: { flushCurrent?: boolean }) => {
    if (vadRafRef.current !== null) {
      cancelAnimationFrame(vadRafRef.current)
      vadRafRef.current = null
    }

    const mr = mediaRecorderRef.current
    mediaRecorderRef.current = null
    if (mr && mr.state !== 'inactive') {
      try {
        if (opts?.flushCurrent) mr.requestData()
      } catch {
        // ignore
      }
      try {
        mr.stop()
      } catch {
        // ignore
      }
    }

    analyserRef.current = null
    const ctx = audioCtxRef.current
    audioCtxRef.current = null
    if (ctx) {
      try {
        void ctx.close()
      } catch {
        // ignore
      }
    }

    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null

    chunksRef.current = []
    speechActiveRef.current = false
    speechStartMsRef.current = null
    speechConfirmMsRef.current = null
    speechConfirmedRef.current = false
    lastVoiceMsRef.current = null
    pendingCommitSinceMsRef.current = null
  }, [])

  React.useEffect(() => () => stopAll({ flushCurrent: false }), [stopAll])

  const ensureListening = React.useCallback(async (): Promise<boolean> => {
    if (disabled) return false
    if (streamRef.current && audioCtxRef.current && analyserRef.current) return true

    let stream: MediaStream
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    } catch (e) {
      console.error('Mic access denied:', e)
      // Per policy: only admit mic unavailable in user UI.
      onStatusRef.current?.({ text: 'Mic unavailable', className: 'error' })
      onHintRef.current?.('Mic unavailable')
      return false
    }

    const mimeType = getMimeType()
    if (!mimeType) {
      onStatusRef.current?.({ text: 'Mic unavailable', className: 'error' })
      stream.getTracks().forEach((t) => t.stop())
      return false
    }

    streamRef.current = stream

    const CtxCtor =
      window.AudioContext ||
      (window as Window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
    const ctx = new CtxCtor()
    audioCtxRef.current = ctx

    const src = ctx.createMediaStreamSource(stream)
    const analyser = ctx.createAnalyser()
    analyser.fftSize = 1024
    analyser.smoothingTimeConstant = 0.15
    src.connect(analyser)
    analyserRef.current = analyser

    baselineRef.current = 0.012
    return true
  }, [disabled, onHint, onStatus])

  const startUtteranceRecording = React.useCallback(() => {
    const stream = streamRef.current
    if (!stream) return
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') return

    const mimeType = getMimeType()
    if (!mimeType) return

    chunksRef.current = []
    const mr = new MediaRecorder(stream, { mimeType })
    mediaRecorderRef.current = mr

    mr.ondataavailable = (e) => {
      if (e.data.size > 0) chunksRef.current.push(e.data)
    }

    mr.onstop = async () => {
      const chunks = chunksRef.current
      chunksRef.current = []

      if (!chunks.length) {
        setIsSubmitting(false)
        isSubmittingRef.current = false
        return
      }

      const blob = new Blob(chunks, { type: mimeType })
      if (blob.size < 1000) {
        setIsSubmitting(false)
        isSubmittingRef.current = false
        onHintRef.current?.('Listening…')
        onStatusRef.current?.({ text: 'Listening…' })
        return
      }

      try {
        await onRecordedRef.current(blob, mimeType)
      } finally {
        setIsSubmitting(false)
        isSubmittingRef.current = false
      }
    }

    mr.start(250)
  }, [onHint, onRecorded, onStatus])

  const stopUtteranceRecording = React.useCallback(() => {
    const mr = mediaRecorderRef.current
    if (!mr || mr.state === 'inactive') return
    try {
      mr.requestData()
    } catch {
      // ignore
    }
    try {
      mr.stop()
    } catch {
      // ignore
    }
  }, [])

  const startVadLoop = React.useCallback(() => {
    const analyser = analyserRef.current
    if (!analyser) return
    if (vadRafRef.current !== null) return

    const timeDomain = new Float32Array(analyser.fftSize)

    const SILENCE_COMMIT_MS = 900
    const COMMIT_GRACE_MS = 150
    const BASELINE_SMOOTHING = 0.02
    const SPEECH_ON_MULT = 2.6
    const SPEECH_OFF_MULT = 1.7
    const MIN_SPEECH_MS = 120
    const CONFIRM_SPEECH_MS = 35
    const MIN_LEVEL_FOR_CONFIRM_MULT = 1.15
    const HINT_UPDATE_MS = 120
    let lastHintMs = 0

    const step = () => {
      vadRafRef.current = requestAnimationFrame(step)

      analyser.getFloatTimeDomainData(timeDomain)
      onAudioFrameRef.current?.(timeDomain)
      const level = rms(timeDomain)

      const baseline = baselineRef.current
      const quietBias = clamp01((baseline * 1.5 - level) / Math.max(1e-6, baseline))
      const alpha = BASELINE_SMOOTHING * (0.2 + 0.8 * quietBias)
      baselineRef.current = baseline * (1 - alpha) + level * alpha

      const now = performance.now()
      const onThresh = Math.max(0.008, baselineRef.current * SPEECH_ON_MULT)
      const offThresh = Math.max(0.006, baselineRef.current * SPEECH_OFF_MULT)

      const isSpeechNow = speechActiveRef.current ? level >= offThresh : level >= onThresh

      if (isSpeechNow) {
        lastVoiceMsRef.current = now
        pendingCommitSinceMsRef.current = null
        if (!speechActiveRef.current) {
          speechActiveRef.current = true
          speechStartMsRef.current = now
          speechConfirmMsRef.current = now
          speechConfirmedRef.current = false
          onStatus?.({ text: 'Listening…', className: 'speaking' })
        }

        const startedAt = speechStartMsRef.current ?? now
        const confirmAt = speechConfirmMsRef.current ?? startedAt
        const speechFor = now - confirmAt
        const confirmLevel = level >= onThresh * MIN_LEVEL_FOR_CONFIRM_MULT
        if (!speechConfirmedRef.current && speechFor >= CONFIRM_SPEECH_MS && confirmLevel) {
          speechConfirmedRef.current = true
          onSpeechStartRef.current?.()
          startUtteranceRecording()
        }

        if (now - lastHintMs >= HINT_UPDATE_MS) {
          lastHintMs = now
          const sec = ((now - startedAt) / 1000).toFixed(1)
          onHintRef.current?.(speechConfirmedRef.current ? `Listening… ${sec}s` : 'Listening…')
        }
        return
      }

      if (!speechActiveRef.current) {
        if (now - lastHintMs >= 700) {
          lastHintMs = now
          onHintRef.current?.('Waiting for speech...')
        }
        return
      }

      const speechStartMs = speechStartMsRef.current ?? now
      const spokeFor = now - speechStartMs
      const lastVoiceMs = lastVoiceMsRef.current ?? speechStartMs
      const silentFor = now - lastVoiceMs

      if (spokeFor < MIN_SPEECH_MS && silentFor > 250) {
        speechActiveRef.current = false
        speechStartMsRef.current = null
        speechConfirmMsRef.current = null
        speechConfirmedRef.current = false
        lastVoiceMsRef.current = null
        return
      }

      if (!speechConfirmedRef.current && silentFor > 220) {
        speechActiveRef.current = false
        speechStartMsRef.current = null
        speechConfirmMsRef.current = null
        speechConfirmedRef.current = false
        lastVoiceMsRef.current = null
        return
      }

      if (silentFor >= SILENCE_COMMIT_MS && !isSubmittingRef.current) {
        if (pendingCommitSinceMsRef.current === null) {
          pendingCommitSinceMsRef.current = now
          return
        }
        if (now - pendingCommitSinceMsRef.current < COMMIT_GRACE_MS) return

        pendingCommitSinceMsRef.current = null
        speechActiveRef.current = false
        speechStartMsRef.current = null
        speechConfirmMsRef.current = null
        speechConfirmedRef.current = false
        lastVoiceMsRef.current = null
        setIsSubmitting(true)
        isSubmittingRef.current = true
        onHintRef.current?.('Thinking of response...')
        onStatusRef.current?.({ text: 'Processing…', className: 'speaking' })
        stopUtteranceRecording()
      } else {
        pendingCommitSinceMsRef.current = null
      }
    }

    vadRafRef.current = requestAnimationFrame(step)
  }, [startUtteranceRecording, stopUtteranceRecording])

  async function startListening() {
    if (disabled || isListening) return
    const ok = await ensureListening()
    if (!ok) return
    setIsListening(true)
    onListeningChangeRef.current?.(true)
    setIsSubmitting(false)
    isSubmittingRef.current = false
    onStatusRef.current?.({ text: 'Listening…' })
    onHintRef.current?.('Waiting for speech...')
    startVadLoop()
  }

  function stopListening() {
    if (!isListening) return
    setIsListening(false)
    onListeningChangeRef.current?.(false)
    setIsSubmitting(false)
    isSubmittingRef.current = false
    onHintRef.current?.('')
    onStatusRef.current?.({ text: 'Ready' })
    stopAll({ flushCurrent: false })
  }

  const hasSupport =
    typeof navigator !== 'undefined' &&
    !!navigator.mediaDevices &&
    typeof navigator.mediaDevices.getUserMedia === 'function' &&
    typeof MediaRecorder !== 'undefined'

  return (
    <button
      className={'mic-btn' + (isListening ? ' recording' : '')}
      id="mic-btn"
      type="button"
      title={hasSupport ? 'Click to start listening, click again to stop' : 'Microphone not supported in this browser'}
      disabled={(!isListening && disabled) || !hasSupport}
      onClick={() => {
        onUserGesture?.()
        if (isListening) {
          onStopInterruptRef.current?.()
          stopListening()
          return
        }
        return void startListening()
      }}
    >
      <svg className="mic-icon" viewBox="0 0 24 24">
        <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm-1-9c0-.55.45-1 1-1s1 .45 1 1v6c0 .55-.45 1-1 1s-1-.45-1-1V5z" />
        <path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z" />
      </svg>
      <svg className="stop-icon" viewBox="0 0 24 24" style={{ display: isListening ? 'block' : 'none' }}>
        <rect x="6" y="6" width="12" height="12" rx="2" />
      </svg>
    </button>
  )
}
