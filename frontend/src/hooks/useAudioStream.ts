import * as React from 'react'

type AudioStreamRefs = {
  stream: MediaStream | null
  context: AudioContext | null
  source: MediaStreamAudioSourceNode | null
}

type EnsureResult = AudioStreamRefs | null

/**
 * Manages mic getUserMedia + AudioContext + MediaStreamSource lifecycle.
 * Single instance shared by VAD + Realtime streamer.
 */
export function useAudioStream(): {
  ensure: () => Promise<EnsureResult>
  ensureRunning: () => Promise<EnsureResult>
  teardown: () => void
  current: () => AudioStreamRefs
} {
  const refs = React.useRef<AudioStreamRefs>({ stream: null, context: null, source: null })

  const resumeIfNeeded = React.useCallback(async (context: AudioContext): Promise<void> => {
    if (context.state !== 'suspended') return
    // Safari can be picky about resume() timing; retry briefly.
    for (let i = 0; i < 4 && context.state === 'suspended'; i++) {
      try {
        await context.resume()
      } catch (e) {
        console.error('AudioContext resume failed', e)
      }
      await new Promise<void>((r) => window.setTimeout(r, 0))
    }
  }, [])

  const teardown = React.useCallback(() => {
    const { stream, context, source } = refs.current
    try {
      source?.disconnect()
    } catch {
      // ignore
    }
    if (context) {
      try {
        void context.close()
      } catch {
        // ignore
      }
    }
    stream?.getTracks().forEach((t) => t.stop())
    refs.current = { stream: null, context: null, source: null }
  }, [])

  const ensure = React.useCallback(async (): Promise<EnsureResult> => {
    if (refs.current.stream && refs.current.context && refs.current.source) {
      await resumeIfNeeded(refs.current.context)
      return refs.current
    }
    let stream: MediaStream
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      })
    } catch (e) {
      console.error('Mic access denied', e)
      return null
    }
    const CtxCtor =
      window.AudioContext ||
      (window as Window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
    const context = new CtxCtor()
    await resumeIfNeeded(context)
    const source = context.createMediaStreamSource(stream)
    refs.current = { stream, context, source }
    return refs.current
  }, [resumeIfNeeded])

  const ensureRunning = React.useCallback(async (): Promise<EnsureResult> => {
    const r = await ensure()
    if (!r?.context) return null
    await resumeIfNeeded(r.context)
    return r.context.state === 'running' ? r : null
  }, [ensure, resumeIfNeeded])

  React.useEffect(() => () => teardown(), [teardown])

  return {
    ensure,
    ensureRunning,
    teardown,
    current: React.useCallback(() => refs.current, []),
  }
}
