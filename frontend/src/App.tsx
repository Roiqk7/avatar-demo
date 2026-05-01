import * as React from 'react'
import { getPersonalities, pipelineAudioStream, pipelineText, pipelineTextStream } from './api/client'
import { AvatarStage } from './components/AvatarStage'
import { ChatComposer } from './components/ChatComposer'
import { ChatPanel, type ChatMessage } from './components/ChatPanel'
import { DevErrorPopup, type DevErrorDetails } from './components/DevErrorPopup'
import { LlmBackendToggle } from './components/LlmBackendToggle'
import { MobileChrome } from './components/MobileChrome'
import { PersonalityPicker } from './components/PersonalityPicker'
import { useLocalStorageState } from './hooks/useLocalStorageState'
import type { ChatTurn, LlmBackend, Personality, PipelineResponse } from './types'
import type { AvatarRenderer } from './rendering/AvatarRenderer'
import { detectSlur } from './safety/slurFilter'

const DEMO_DISCLAIMER_TEXT =
  'Please note this is just a technical demo, not an actual Signosoft product. I vibe-coded this, so please be kind.'
const IDLE_DVD_DELAY_MS = 12_000

function domainLabelForUrl(url: string): string {
  const raw = (url || '').trim()
  if (!raw) return 'link'
  try {
    const u = raw.startsWith('http://') || raw.startsWith('https://') ? new URL(raw) : new URL(`http://${raw}`)
    const host = (u.hostname || '').toLowerCase().replace(/^\.+/, '')
    const parts = host.split('.').filter(Boolean)
    if (!parts.length) return 'link'
    const core = parts.length >= 2 ? parts.slice(-2).join('.') : parts[0]!
    if (core === 'signosoft.com') return 'Signosoft'
    return core
  } catch {
    return 'link'
  }
}

function prettifyUrlsToMarkdown(text: string): string {
  // Convert raw URLs to clickable markdown links: https://x/y -> [x.com](https://x/y)
  // Avoid rewriting already-markdown links by skipping matches immediately preceded by '(' after ']'.
  const re = /\bhttps?:\/\/[^\s<>()]+|\bwww\.[^\s<>()]+/gi
  return (text || '').replace(re, (match: string, offset: number, full: string) => {
    const prev = full.slice(Math.max(0, offset - 2), offset)
    if (prev === '](') return match
    const href = match.toLowerCase().startsWith('http') ? match : `https://${match}`
    const label = domainLabelForUrl(href)
    return `[${label}](${href})`
  })
}

function prettifyBracketMathToKatex(text: string): string {
  // Many models emit display-math as `[ ... ]` instead of `\\[ ... \\]` or `$$...$$`.
  // Convert bracket-math to `$$...$$` when it looks like LaTeX.
  // Heuristic: contains a backslash command or _ or ^ or \\times.
  const s = text || ''
  return s.replace(/\[\s*([\s\S]*?)\s*\]/g, (full, inner: string) => {
    const t = String(inner || '')
    const looksLatex = /\\[A-Za-z]+|[_^]|\\times|\\left|\\right/.test(t)
    if (!looksLatex) return full
    return `\n\n$$\n${t}\n$$\n\n`
  })
}

function ControlsPanel(props: {
  llmBackend: LlmBackend
  onLlmBackendChange: (value: LlmBackend) => void
  personalities: Personality[]
  activeId: string | null
  onSelectPersonality: (id: string) => void
  disabled: boolean
}) {
  return (
    <div className="section">
      <div className="section-title">LLM</div>
      <LlmBackendToggle value={props.llmBackend} onChange={props.onLlmBackendChange} disabled={props.disabled} />
      <div style={{ height: 14 }} />
      <div className="section-title">Personality</div>
      <PersonalityPicker
        personalities={props.personalities.filter((p) => p.id !== 'signoface')}
        activeId={props.activeId}
        onSelect={props.onSelectPersonality}
        disabled={props.disabled}
      />
    </div>
  )
}

function App() {
  const sessionId = React.useRef(crypto.randomUUID()).current
  const [personalities, setPersonalities] = React.useState<Personality[]>([])
  const [currentPersonality, setCurrentPersonality] = React.useState<Personality | null>(null)
  const [renderer, setRenderer] = React.useState<AvatarRenderer | null>(null)
  const [messages, setMessages] = React.useState<ChatMessage[]>([])
  const historyRef = React.useRef<ChatTurn[]>([])

  const [llmBackend, setLlmBackend] = useLocalStorageState<LlmBackend>('avatarDemo.llmBackend', 'echo')
  const [activeBg, setActiveBg] = React.useState(3)
  const [isOptionsOpen, setIsOptionsOpen] = React.useState(false)

  const [isProcessing, setIsProcessing] = React.useState(false)
  const [hud, setHud] = React.useState('Loading assets...')
  const [debug, setDebug] = React.useState<{
    lang?: string | null
    score?: number | null
    lang_mode?: string | null
    session_lang?: string | null
    voice?: string | null
    voice_mode?: string | null
    enabled?: boolean
    error?: string | null
    stt?: string
    llm?: string
    tts?: string
    detector?: string
    timing_stt_ms?: number | null
    timing_llm_ms?: number | null
    timing_tts_ms?: number | null
  }>({})
  const [text, setText] = React.useState('')
  const [isSpeakingClass, setIsSpeakingClass] = React.useState(false)
  const [composerNotice, setComposerNotice] = React.useState('')
  const [devError, setDevError] = React.useState<DevErrorDetails | null>(null)
  const [micModeOn, setMicModeOn] = React.useState(false)
  const [micHint, setMicHint] = React.useState('')
  const [pipelineStage, setPipelineStage] = React.useState<'stt' | 'llm' | 'speaking' | null>(null)
  const [pipelineStageStart, setPipelineStageStart] = React.useState<number | null>(null)
  const interruptedTimeoutRef = React.useRef<number | null>(null)
  const longRequestTimeoutRef = React.useRef<number | null>(null)

  const devPopupsEnabled =
    (import.meta as ImportMeta & { env?: Record<string, string> }).env?.VITE_DEV_ERROR_POPUPS === '1'

  const queuedDisclaimerRef = React.useRef(false)
  const requestAbortRef = React.useRef<AbortController | null>(null)
  const activeRequestIdRef = React.useRef(0)
  const isProcessingRef = React.useRef(false)
  React.useLayoutEffect(() => {
    isProcessingRef.current = isProcessing
  })

  React.useEffect(() => {
    const id = setInterval(() => {
      setActiveBg((prev) => {
        let next: number
        do {
          next = Math.floor(Math.random() * 6)
        } while (next === prev)
        return next
      })
    }, 20000)
    return () => clearInterval(id)
  }, [])

  // Prevent mic status text (e.g. "Listening...") from lingering when mic mode is off.
  React.useEffect(() => {
    if (micModeOn) return
    if (pipelineStage) return
    if (composerNotice.trim()) return
    if (!micHint) return
    setMicHint('')
    setPipelineStageStart(null)
  }, [composerNotice, micHint, micModeOn, pipelineStage])

  React.useEffect(() => {
    let mounted = true
    ;(async () => {
      try {
        const ps = await getPersonalities()
        if (!mounted) return
        setPersonalities(ps)
        const defaultP = ps.find((p) => p.id === 'peter') || ps[0] || null
        setCurrentPersonality(defaultP)
      } catch (e) {
        console.error('Failed to load personalities', e)
      }
    })()
    return () => {
      mounted = false
    }
  }, [])

  React.useEffect(() => {
    if (!isOptionsOpen) return
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setIsOptionsOpen(false)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [isOptionsOpen])

  const beginNewRequest = React.useCallback(
    (opts?: { stopAudio?: boolean }) => {
      activeRequestIdRef.current += 1
      requestAbortRef.current?.abort()
      requestAbortRef.current = new AbortController()
      if (opts?.stopAudio !== false) renderer?.interrupt()
      return { requestId: activeRequestIdRef.current, signal: requestAbortRef.current.signal }
    },
    [renderer],
  )

  const personalityNameRef = React.useRef(currentPersonality?.display_name || 'Avatar')
  React.useEffect(() => {
    personalityNameRef.current = currentPersonality?.display_name || 'Avatar'
  }, [currentPersonality?.display_name])

  const addMessage = React.useCallback((text: string, isUser: boolean, opts?: { isMarkdown?: boolean }) => {
    const label = isUser ? 'You' : personalityNameRef.current
    setMessages((m) => [...m, { id: crypto.randomUUID(), label, text, isUser, isMarkdown: opts?.isMarkdown }])
  }, [])

  const addMessageWithId = React.useCallback((id: string, text: string, isUser: boolean, opts?: { isMarkdown?: boolean }) => {
    const label = isUser ? 'You' : personalityNameRef.current
    setMessages((m) => [...m, { id, label, text, isUser, isMarkdown: opts?.isMarkdown }])
  }, [])

  const updateMessageText = React.useCallback((id: string, text: string) => {
    setMessages((m) => m.map((msg) => (msg.id === id ? { ...msg, text } : msg)))
  }, [])

  const lastActiveMsRef = React.useRef<number>(0)
  const [dvdMode, setDvdMode] = React.useState(false)
  const ouchRecenterTimeoutRef = React.useRef<number | null>(null)
  React.useEffect(() => {
    lastActiveMsRef.current = performance.now()
  }, [])

  const markActive = React.useCallback(
    (opts?: { recenter?: boolean }) => {
      lastActiveMsRef.current = performance.now()
      if (dvdMode) setDvdMode(false)
      if (renderer) {
        renderer.setDvdMode(false)
        if (opts?.recenter) renderer.recenterDvd({ animateMs: 200 })
      }
    },
    [dvdMode, renderer],
  )

  const playResponse = React.useCallback(
    async (data: Pick<PipelineResponse, 'audio_base64' | 'visemes'>) => {
      if (!data.audio_base64 || !renderer) return
      setIsSpeakingClass(true)
      const keepAliveId = window.setInterval(() => {
        lastActiveMsRef.current = performance.now()
        renderer.setDvdMode(false)
      }, 1000)
      try {
        await renderer.playTts(data.audio_base64, data.visemes, () => {}, (err) => {
          console.error('Audio playback error:', err)
          setComposerNotice('Audio playback failed. Please try again.')
        })
      } finally {
        window.clearInterval(keepAliveId)
        setIsSpeakingClass(false)
      }
    },
    [renderer],
  )

  const speakEchoText = React.useCallback(
    async (t: string, pid: string): Promise<PipelineResponse> => {
      const data = await pipelineText({
        text: t,
        personality_id: pid,
        llm_backend: 'echo',
        session_id: sessionId,
        history: [],
      })
      await playResponse(data)
      return data
    },
    [playResponse, sessionId],
  )

  const meme67CacheRef = React.useRef<Map<string, PipelineResponse>>(new Map())

  const run67MemePhase = React.useCallback(
    async (pid: string): Promise<void> => {
      if (!renderer) return
      await new Promise<void>((resolve) => window.setTimeout(resolve, 600))
      let chunk = meme67CacheRef.current.get(pid) || null
      if (!chunk) {
        chunk = await pipelineText({
          text: '67',
          personality_id: pid,
          llm_backend: 'echo',
          session_id: sessionId,
          history: [],
        })
        meme67CacheRef.current.set(pid, chunk)
      }
      const phaseMs = 2000
      const startMs = performance.now()
      renderer.startSpeechRotation({ turns: 6, durationMs: phaseMs })
      await playResponse(chunk)
      const elapsed = performance.now() - startMs
      const remaining = Math.max(0, phaseMs - elapsed)
      if (remaining > 0) await new Promise<void>((resolve) => window.setTimeout(resolve, remaining))
    },
    [playResponse, renderer, sessionId],
  )

  React.useEffect(() => {
    return () => {
      if (ouchRecenterTimeoutRef.current !== null) {
        window.clearTimeout(ouchRecenterTimeoutRef.current)
        ouchRecenterTimeoutRef.current = null
      }
    }
  }, [])

  React.useEffect(() => {
    const onKey = () => {
      // Safari requires AudioContext resume to be initiated from a user gesture.
      void renderer?.audioPlayer.unlock()
      markActive({ recenter: true })
    }
    const onPointer = (e: PointerEvent) => {
      // Safari requires AudioContext resume to be initiated from a user gesture.
      void renderer?.audioPlayer.unlock()
      const target = e.target as Element | null
      if (target?.closest?.('#avatar-canvas')) markActive({ recenter: false })
      else markActive({ recenter: true })
    }
    const onFocus = () => markActive({ recenter: true })
    const onVisibility = () => {
      if (document.visibilityState === 'visible') markActive({ recenter: true })
    }
    window.addEventListener('keydown', onKey)
    window.addEventListener('pointerdown', onPointer)
    window.addEventListener('focus', onFocus)
    document.addEventListener('visibilitychange', onVisibility)
    const id = window.setInterval(() => {
      const idleFor = performance.now() - lastActiveMsRef.current
      const should = idleFor >= IDLE_DVD_DELAY_MS && !isProcessing
      if (should !== dvdMode) setDvdMode(should)
      if (renderer) renderer.setDvdMode(should)
    }, 250)
    return () => {
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('pointerdown', onPointer)
      window.removeEventListener('focus', onFocus)
      document.removeEventListener('visibilitychange', onVisibility)
      window.clearInterval(id)
    }
  }, [dvdMode, isProcessing, markActive, renderer])

  const sendUserText = React.useCallback(
    async (
      msg: string,
      opts?: { llmBackendOverride?: LlmBackend; onReplyReady?: () => void; displayText?: string },
    ): Promise<void> => {
      const trimmed = msg.trim()
      if (!trimmed || isProcessingRef.current) return
      const pid = currentPersonality?.id || 'peter'
      const backend: LlmBackend = opts?.llmBackendOverride ?? llmBackend
      void renderer?.audioPlayer.unlock()
      markActive({ recenter: true })
      setIsProcessing(true)
      addMessage(opts?.displayText ?? trimmed, true)

      try {
        const { requestId, signal } = beginNewRequest()
        if (longRequestTimeoutRef.current !== null) window.clearTimeout(longRequestTimeoutRef.current)
        longRequestTimeoutRef.current = window.setTimeout(() => {
          longRequestTimeoutRef.current = null
          if (requestId === activeRequestIdRef.current) {
            setComposerNotice('This is taking unusually long…')
          }
        }, 10_000)
        if (trimmed === 'signoface') {
          const p = personalities.find((x) => x.id === 'signoface') || null
          if (p) {
            setCurrentPersonality(p)
            await renderer?.applyPersonality(p)
          }
          opts?.onReplyReady?.()
          await speakEchoText("It's signing time!", p?.id || pid)
          return
        }
        const slur = detectSlur(trimmed)
        if (slur) renderer?.setMood('sad')
        let memeRan = false
        if (trimmed.includes('67')) {
          memeRan = true
          opts?.onReplyReady?.()
          await run67MemePhase(pid)
        }
        const historySnapshot = historyRef.current.slice()
        let data: PipelineResponse | null = null

        if (backend === 'max') {
          const assistantMsgId = crypto.randomUUID()
          addMessageWithId(assistantMsgId, '', false, { isMarkdown: true })
          let streamedText = ''
          let gotAudio = false
          const audioBySeq = new Map<number, { audio_base64: string; visemes: PipelineResponse['visemes'] }>()
          let nextSeq = 0
          let maxSeqSeen = -1
          let draining = false
          const notifyWaiters: Array<() => void> = []

          const waitForAudioOrTimeout = (ms: number) =>
            new Promise<'signal' | 'timeout'>((resolve) => {
              const onSignal = () => resolve('signal')
              notifyWaiters.push(onSignal)
              window.setTimeout(() => resolve('timeout'), ms)
            })

          const notifyAudio = () => {
            while (notifyWaiters.length) {
              const fn = notifyWaiters.shift()
              try {
                fn?.()
              } catch {
                // ignore
              }
            }
          }

          const drainAudio = async () => {
            if (draining) return
            draining = true
            try {
              while (true) {
                if (requestId !== activeRequestIdRef.current) return
                const item = audioBySeq.get(nextSeq) || null
                if (item) {
                  audioBySeq.delete(nextSeq)
                  nextSeq += 1
                  if (renderer) {
                    const ok = await renderer.queueTtsChunk(item.audio_base64, item.visemes)
                    if (!ok) {
                      await playResponse(item)
                    }
                  } else {
                    await playResponse(item)
                  }
                  continue
                }

                // Missing next chunk: wait briefly, but never play out of order.
                const hasLater = [...audioBySeq.keys()].some((k) => k > nextSeq)
                if (!hasLater) break
                const r = await waitForAudioOrTimeout(1500)
                if (r === 'timeout') break
              }
            } finally {
              draining = false
            }
          }

          for await (const evt of pipelineTextStream({
            text: trimmed,
            personality_id: pid,
            llm_backend: backend,
            session_id: sessionId,
            history: historySnapshot,
            safety_hint_language: slur?.language,
            signal,
          })) {
            if (requestId !== activeRequestIdRef.current) return
            if (evt.type === 'delta') {
              streamedText += evt.delta
              updateMessageText(assistantMsgId, prettifyBracketMathToKatex(prettifyUrlsToMarkdown(streamedText)))
              continue
            }
            if (evt.type === 'audio') {
              gotAudio = true
              maxSeqSeen = Math.max(maxSeqSeen, evt.seq)
              audioBySeq.set(evt.seq, { audio_base64: evt.audio_base64, visemes: evt.visemes })
              notifyAudio()
              void drainAudio()
              continue
            }
            if (evt.type === 'done') {
              data = evt.data
              break
            }
            if (evt.type === 'error') {
              throw new Error(evt.message || 'Something went wrong. Please try again.')
            }
          }
          if (!data) throw new Error('No response received.')
          if (!data.response_text && streamedText) data.response_text = streamedText
          updateMessageText(
            assistantMsgId,
            prettifyBracketMathToKatex(prettifyUrlsToMarkdown(data.response_text || streamedText)),
          )
          // Ensure any already-arrived chunks are drained before deciding on fallback.
          await drainAudio()
          const gapLikely = gotAudio && (audioBySeq.size > 0 || (maxSeqSeen >= 0 && nextSeq <= maxSeqSeen))
          if (!gotAudio || gapLikely) {
            // Reliability fallback: play full TTS from the done payload (backend guarantees this now).
            await playResponse(data)
          }
        } else {
          data = await pipelineText({
            text: trimmed,
            personality_id: pid,
            llm_backend: backend,
            session_id: sessionId,
            history: historySnapshot,
            safety_hint_language: slur?.language,
            signal,
          })
        }
        if (requestId !== activeRequestIdRef.current) return
        if (longRequestTimeoutRef.current !== null) {
          window.clearTimeout(longRequestTimeoutRef.current)
          longRequestTimeoutRef.current = null
        }
        setDebug((prev) => {
          const nextLlm =
            (data.debug_llm_backend === 'openai' || data.debug_llm_backend === 'max'
              ? data.debug_llm_model || data.debug_llm_backend
              : data.debug_llm_backend) ?? prev.llm ?? llmBackend
          const nextTts = data.debug_tts_backend ?? prev.tts ?? 'azure-speech'
          return {
            ...prev,
            lang: data.detected_language,
            score: data.detected_language_score,
            lang_mode: data.debug_lang_mode ?? null,
            session_lang: data.debug_session_lang ?? prev.session_lang ?? null,
            voice: data.voice_used,
            voice_mode: data.debug_voice_mode ?? null,
            enabled: data.language_detection_enabled,
            error: data.language_detection_error ?? null,
            stt:
              data.debug_stt_model && data.debug_stt_language
                ? `${data.debug_stt_model} (${data.debug_stt_language})`
                : data.debug_stt_model ?? undefined,
            llm: nextLlm,
            tts: nextTts,
            detector: data.debug_lang_detect_backend ?? undefined,
            timing_stt_ms: data.timing_stt_ms ?? null,
            timing_llm_ms: data.timing_llm_ms ?? null,
            timing_tts_ms: data.timing_tts_ms ?? null,
          }
        })
        renderer?.setMood(data.mood ?? 'neutral')
        if (backend !== 'max') addMessage(data.response_text, false)
        historyRef.current = [
          ...historySnapshot,
          { role: 'user', content: trimmed },
          { role: 'assistant', content: data.response_text || '' },
        ]
        if (!memeRan && data.response_text.includes('67')) {
          memeRan = true
          opts?.onReplyReady?.()
          await run67MemePhase(pid)
        }
        opts?.onReplyReady?.()
        if (backend !== 'max') await playResponse(data)
        renderer?.setMood('neutral')
      } catch (e) {
        if (e instanceof DOMException && e.name === 'AbortError') return
        console.error('sendUserText failed', e)
        setComposerNotice('Something went wrong. Please try again.')
        if (devPopupsEnabled) {
          const err = e as Error
          setDevError({
            title: 'Text pipeline failed',
            message: String(err?.message || e),
            stack: err?.stack,
          })
        }
      } finally {
        if (longRequestTimeoutRef.current !== null) {
          window.clearTimeout(longRequestTimeoutRef.current)
          longRequestTimeoutRef.current = null
        }
        setIsProcessing(false)
      }
    },
    [
      addMessage,
      beginNewRequest,
      currentPersonality?.id,
      devPopupsEnabled,
      llmBackend,
      markActive,
      personalities,
      playResponse,
      renderer,
      run67MemePhase,
      sessionId,
      speakEchoText,
    ],
  )

  const handleUtteranceBlob = React.useCallback(
    async (blob: Blob, mimeType: string): Promise<void> => {
      const pid = currentPersonality?.id || 'peter'
      void renderer?.audioPlayer.unlock()
      markActive({ recenter: true })
      setIsProcessing(true)
      setPipelineStage('stt')
      setPipelineStageStart(Date.now())
      setMicHint('Transcribing…')
      try {
        const { requestId, signal } = beginNewRequest()
        if (longRequestTimeoutRef.current !== null) window.clearTimeout(longRequestTimeoutRef.current)
        longRequestTimeoutRef.current = window.setTimeout(() => {
          longRequestTimeoutRef.current = null
          if (requestId === activeRequestIdRef.current) {
            setComposerNotice('This is taking unusually long…')
          }
        }, 10_000)

        const historySnapshot = historyRef.current.slice()
        let data: PipelineResponse | null = null
        const assistantMsgId = crypto.randomUUID()
        let streamedText = ''
        let gotAudio = false
        const audioBySeq = new Map<number, { audio_base64: string; visemes: PipelineResponse['visemes'] }>()
        let nextSeq = 0
        let draining = false
        const notifyWaiters: Array<() => void> = []

        const waitForAudioOrTimeout = (ms: number) =>
          new Promise<'signal' | 'timeout'>((resolve) => {
            const onSignal = () => resolve('signal')
            notifyWaiters.push(onSignal)
            window.setTimeout(() => resolve('timeout'), ms)
          })

        const notifyAudio = () => {
          while (notifyWaiters.length) {
            const fn = notifyWaiters.shift()
            try {
              fn?.()
            } catch {
              // ignore
            }
          }
        }

        const drainAudio = async () => {
          if (draining) return
          draining = true
          try {
            while (true) {
              if (requestId !== activeRequestIdRef.current) return
              const item = audioBySeq.get(nextSeq) || null
              if (item) {
                audioBySeq.delete(nextSeq)
                nextSeq += 1
                if (renderer) {
                  const ok = await renderer.queueTtsChunk(item.audio_base64, item.visemes)
                  if (!ok) {
                    await playResponse(item)
                  }
                } else {
                  await playResponse(item)
                }
                continue
              }

              const hasLater = [...audioBySeq.keys()].some((k) => k > nextSeq)
              if (!hasLater) break
              const r = await waitForAudioOrTimeout(1500)
              if (r === 'timeout') break
            }
          } finally {
            draining = false
          }
        }
        for await (const evt of pipelineAudioStream({
          blob,
          mimeType,
          personality_id: pid,
          llm_backend: llmBackend,
          session_id: sessionId,
          history: historySnapshot,
          interaction_mode: 'listening',
          signal,
        })) {
          if (requestId !== activeRequestIdRef.current) return
          if (evt.type === 'stt') {
            const userText = evt.user_text || ''
            if (userText) addMessage(`🎤 ${userText}`, true)
            if (llmBackend === 'max') addMessageWithId(assistantMsgId, '', false, { isMarkdown: true })
            setPipelineStage('llm')
            setPipelineStageStart(Date.now())
            setMicHint('Thinking about the response…')
            continue
          }
          if (evt.type === 'delta') {
            if (pipelineStage !== 'llm') {
              setPipelineStage('llm')
              setPipelineStageStart(Date.now())
            }
            setMicHint('Thinking about the response…')
            if (llmBackend === 'max') {
              streamedText += evt.delta
              updateMessageText(assistantMsgId, prettifyBracketMathToKatex(prettifyUrlsToMarkdown(streamedText)))
            }
            continue
          }
          if (evt.type === 'audio') {
            if (llmBackend === 'max') {
              gotAudio = true
              audioBySeq.set(evt.seq, { audio_base64: evt.audio_base64, visemes: evt.visemes })
              notifyAudio()
              void drainAudio()
            }
            continue
          }
          if (evt.type === 'done') {
            data = evt.data
            break
          }
          if (evt.type === 'error') {
            throw new Error(evt.message || 'Something went wrong. Please try again.')
          }
        }
        if (!data) throw new Error('No response received.')
        if (requestId !== activeRequestIdRef.current) return
        if (longRequestTimeoutRef.current !== null) {
          window.clearTimeout(longRequestTimeoutRef.current)
          longRequestTimeoutRef.current = null
        }
        setDebug((prev) => {
          const nextLlm =
            (data.debug_llm_backend === 'openai' || data.debug_llm_backend === 'max'
              ? data.debug_llm_model || data.debug_llm_backend
              : data.debug_llm_backend) ?? prev.llm ?? llmBackend
          const nextTts = data.debug_tts_backend ?? prev.tts ?? 'azure-speech'
          return {
            ...prev,
            lang: data.detected_language,
            score: data.detected_language_score,
            lang_mode: data.debug_lang_mode ?? null,
            session_lang: data.debug_session_lang ?? prev.session_lang ?? null,
            voice: data.voice_used,
            voice_mode: data.debug_voice_mode ?? null,
            enabled: data.language_detection_enabled,
            error: data.language_detection_error ?? null,
            stt:
              data.debug_stt_model && data.debug_stt_language
                ? `${data.debug_stt_model} (${data.debug_stt_language})`
                : data.debug_stt_model ?? undefined,
            llm: nextLlm,
            tts: nextTts,
            detector: data.debug_lang_detect_backend ?? undefined,
            timing_stt_ms: data.timing_stt_ms ?? null,
            timing_llm_ms: data.timing_llm_ms ?? null,
            timing_tts_ms: data.timing_tts_ms ?? null,
          }
        })
        renderer?.setMood(data.mood ?? 'neutral')
        if (llmBackend === 'max') {
          updateMessageText(
            assistantMsgId,
            prettifyBracketMathToKatex(prettifyUrlsToMarkdown(data.response_text || streamedText)),
          )
          if (!gotAudio) {
            await playResponse(data)
          }
        } else {
          if (data.response_text) addMessage(data.response_text, false)
        }
        historyRef.current = [
          ...historySnapshot,
          { role: 'user', content: data.user_text || '' },
          { role: 'assistant', content: data.response_text || '' },
        ]
        setPipelineStage('speaking')
        setPipelineStageStart(null)
        setMicHint('Speaking...')
        if (llmBackend !== 'max') await playResponse(data)
        renderer?.setMood('neutral')
      } catch (e) {
        if (e instanceof DOMException && e.name === 'AbortError') return
        console.error('handleUtteranceBlob failed', e)
        setComposerNotice('Something went wrong. Please try again.')
        if (devPopupsEnabled) {
          const err = e as Error
          setDevError({
            title: 'Mic pipeline failed',
            message: String(err?.message || e),
            stack: err?.stack,
          })
        }
      } finally {
        if (longRequestTimeoutRef.current !== null) {
          window.clearTimeout(longRequestTimeoutRef.current)
          longRequestTimeoutRef.current = null
        }
        setIsProcessing(false)
        setPipelineStage(null)
        setPipelineStageStart(null)
      }
    },
    [addMessage, beginNewRequest, currentPersonality?.id, devPopupsEnabled, llmBackend, markActive, pipelineStage, playResponse, renderer, sessionId],
  )

  // Auto-clear non-critical notice.
  React.useEffect(() => {
    if (!composerNotice) return
    const id = window.setTimeout(() => setComposerNotice(''), 3500)
    return () => window.clearTimeout(id)
  }, [composerNotice])

  React.useEffect(() => {
    return () => {
      if (interruptedTimeoutRef.current !== null) {
        window.clearTimeout(interruptedTimeoutRef.current)
        interruptedTimeoutRef.current = null
      }
    }
  }, [])

  const userEditedRef = React.useRef(false)

  async function sendText() {
    const msg = text.trim()
    if (!msg || isProcessing) return
    setText('')
    await sendUserText(msg)
  }

  const sendDemoDisclaimer = React.useCallback(() => {
    queuedDisclaimerRef.current = false
    void sendUserText(DEMO_DISCLAIMER_TEXT, { llmBackendOverride: 'echo' })
  }, [sendUserText])

  React.useEffect(() => {
    if (!isProcessing && queuedDisclaimerRef.current) {
      window.setTimeout(() => sendDemoDisclaimer(), 0)
    }
  }, [isProcessing, sendDemoDisclaimer])

  function selectPersonality(id: string) {
    if (isProcessing) return
    const p = personalities.find((x) => x.id === id) || null
    if (!p) return
    setCurrentPersonality(p)
  }

  const onAvatarClick = React.useCallback(() => {
    if (isProcessing) return
    void (async () => {
      const dvd = renderer?.getDvdModeEnabled() ?? false
      renderer?.triggerBlackHole({ recenterToCanvas: !dvd })
      const pid = currentPersonality?.id || 'peter'
      markActive({ recenter: !dvd })
      setIsProcessing(true)
      if (ouchRecenterTimeoutRef.current !== null) {
        window.clearTimeout(ouchRecenterTimeoutRef.current)
        ouchRecenterTimeoutRef.current = null
      }
      const ouchAnimMs = renderer?.getBlackHoleTotalMs() ?? 3800
      ouchRecenterTimeoutRef.current = window.setTimeout(() => {
        ouchRecenterTimeoutRef.current = null
        markActive({ recenter: true })
      }, ouchAnimMs)
      try {
        await speakEchoText('ouch', pid)
      } finally {
        setIsProcessing(false)
      }
    })()
  }, [currentPersonality?.id, isProcessing, markActive, renderer, speakEchoText])

  const controlsPanel = (
    <ControlsPanel
      llmBackend={llmBackend}
      onLlmBackendChange={setLlmBackend}
      personalities={personalities}
      activeId={currentPersonality?.id || null}
      onSelectPersonality={selectPersonality}
      disabled={isProcessing}
    />
  )

  return (
    <>
      <div className="grain" />
      <button
        type="button"
        className="demo-disclaimer-btn"
        onClick={() => {
          if (isProcessing) {
            queuedDisclaimerRef.current = true
            return
          }
          sendDemoDisclaimer()
        }}
        aria-label="Send demo disclaimer"
        title="Send demo disclaimer"
      >
        Demo disclaimer
      </button>
      <header>
        <div className="logo">
          <a className="logo-link" href="https://ai-avatar.signosoft.com">
            <img src="/logo_full.png" alt="Signosoft" className="logo-img" />
          </a>
        </div>
        <div className="header-subtitle">Avatar demo</div>
      </header>

      <MobileChrome
        isOptionsOpen={isOptionsOpen}
        onOpen={() => setIsOptionsOpen(true)}
        onClose={() => setIsOptionsOpen(false)}
        optionsContent={controlsPanel}
      />

      <div className="main-layout">
        <AvatarStage
          personality={currentPersonality}
          isSpeakingClass={isSpeakingClass}
          activeBg={activeBg}
          hud={hud}
          debug={debug}
          onRenderer={(r) => {
            setRenderer(r)
            if (r) r.onError = (msg) => console.error('Renderer error', msg)
          }}
          onHud={setHud}
          onAvatarClick={onAvatarClick}
        />

        <div className="sidebar">
          <div className="desktop-controls">{controlsPanel}</div>
          <ChatPanel messages={messages} />
          <ChatComposer
            text={text}
            onTextChange={(v) => {
              userEditedRef.current = true
              setText(v)
            }}
            onSend={() => void sendText()}
            onTextFocus={() => markActive({ recenter: true })}
            isProcessing={isProcessing}
            micModeOn={micModeOn}
            onMicModeChange={setMicModeOn}
            micHint={micHint}
            micNotice={composerNotice}
            onMicHint={setMicHint}
            pipelineStage={pipelineStage}
            timerStartMs={pipelineStageStart}
            onMicRecorded={(blob, mimeType) => handleUtteranceBlob(blob, mimeType)}
            onMicSpeechStart={() => {
              // Barge-in: cancel in-flight request and stop audio immediately.
              beginNewRequest()
              const didInterrupt = isProcessingRef.current || isSpeakingClass
              if (isProcessingRef.current) setIsProcessing(false)
              setPipelineStage(null)
              setPipelineStageStart(null)
              if (didInterrupt) {
                setMicHint('Interrupted')
                if (interruptedTimeoutRef.current !== null) window.clearTimeout(interruptedTimeoutRef.current)
                interruptedTimeoutRef.current = window.setTimeout(() => {
                  interruptedTimeoutRef.current = null
                  setMicHint('Listening...')
                }, 1000)
              }
            }}
            onMicStopInterrupt={() => {
              // Stop-click interrupt (only relevant when mic is actively listening).
              beginNewRequest()
              const didInterrupt = isProcessingRef.current || isSpeakingClass
              if (isProcessingRef.current) setIsProcessing(false)
              setPipelineStage(null)
              setPipelineStageStart(null)
              if (didInterrupt) {
                setMicHint('Interrupted')
                if (interruptedTimeoutRef.current !== null) window.clearTimeout(interruptedTimeoutRef.current)
                interruptedTimeoutRef.current = window.setTimeout(() => {
                  interruptedTimeoutRef.current = null
                  setMicHint('Listening...')
                }, 1000)
              }
            }}
            onMicGesture={() => {
              void renderer?.audioPlayer.unlock()
              markActive({ recenter: true })
            }}
          />
        </div>
      </div>

      {devPopupsEnabled ? <DevErrorPopup error={devError} onClose={() => setDevError(null)} /> : null}
    </>
  )
}

export default App
