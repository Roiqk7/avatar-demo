import * as React from 'react'
import { getPersonalities, pipelineAudio, pipelineText } from './api/client'
import { AvatarCanvas } from './components/AvatarCanvas'
import { ChatPanel, type ChatMessage } from './components/ChatPanel'
import { LlmBackendToggle } from './components/LlmBackendToggle'
import { MicButton } from './components/MicButton'
import { PersonalityPicker } from './components/PersonalityPicker'
import { useLocalStorageState } from './hooks/useLocalStorageState'
import type { LlmBackend, Personality, PipelineResponse } from './types'
import type { AvatarRenderer } from './rendering/AvatarRenderer'
import { detectSlur } from './safety/slurFilter'

function App() {
  const sessionId = React.useRef(crypto.randomUUID()).current
  const [personalities, setPersonalities] = React.useState<Personality[]>([])
  const [currentPersonality, setCurrentPersonality] = React.useState<Personality | null>(null)
  const [renderer, setRenderer] = React.useState<AvatarRenderer | null>(null)
  const [messages, setMessages] = React.useState<ChatMessage[]>([])

  const [llmBackend, setLlmBackend] = useLocalStorageState<LlmBackend>('avatarDemo.llmBackend', 'echo')
  const [activeBg, setActiveBg] = React.useState(3) // start with Serenity (blue)
  const [isOptionsOpen, setIsOptionsOpen] = React.useState(false)

  React.useEffect(() => {
    const id = setInterval(() => {
      setActiveBg(prev => {
        let next: number
        do { next = Math.floor(Math.random() * 6) } while (next === prev)
        return next
      })
    }, 20000)
    return () => clearInterval(id)
  }, [])

  const [isProcessing, setIsProcessing] = React.useState(false)
  const [status, setStatus] = React.useState<{ text: string; className?: string }>({ text: 'Initializing...' })
  const [hud, setHud] = React.useState('Loading assets...')
  const [assetError, setAssetError] = React.useState<string | null>(null)
  const [micHint, setMicHint] = React.useState('')
  const [debug, setDebug] = React.useState<{
    lang?: string | null
    score?: number | null
    voice?: string | null
    enabled?: boolean
    error?: string | null
  }>({})
  const [text, setText] = React.useState('')

  React.useEffect(() => {
    let mounted = true
    ;(async () => {
      try {
        const ps = await getPersonalities()
        if (!mounted) return
        setPersonalities(ps)
        const defaultP = ps.find((p) => p.id === 'peter') || ps[0] || null
        setCurrentPersonality(defaultP)
        setStatus({ text: defaultP ? `Ready — ${defaultP.display_name}` : 'Ready' })
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e)
        setStatus({ text: 'Failed to load personalities', className: 'error' })
        setMessages([{ id: crypto.randomUUID(), label: 'System', text: msg, isUser: false }])
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

  async function selectPersonality(id: string) {
    if (isProcessing) return
    const p = personalities.find((x) => x.id === id) || null
    if (!p) return
    setCurrentPersonality(p)
    setStatus({ text: `Loading ${p.display_name}...` })
    // renderer.applyPersonality is triggered by effect once renderer exists
    setStatus({ text: `Ready — ${p.display_name}` })
  }

  function addMessage(text: string, isUser: boolean) {
    const label = isUser ? 'You' : currentPersonality?.display_name || 'Avatar'
    setMessages((m) => [...m, { id: crypto.randomUUID(), label, text, isUser }])
  }

  async function playResponse(data: Pick<PipelineResponse, 'audio_base64' | 'visemes'>) {
    if (!data.audio_base64) {
      setStatus({ text: 'Ready (no audio)' })
      return
    }
    if (!renderer) return
    setStatus({ text: 'Speaking', className: 'speaking' })
    // While speaking, keep resetting the idle timer so DVD/pong mode can't kick in mid-utterance.
    // We avoid recentering here to prevent any visible snaps during playback.
    const keepAliveId = window.setInterval(() => {
      lastActiveMsRef.current = performance.now()
      renderer.setDvdMode(false)
    }, 1000)
    try {
      await renderer.playTts(data.audio_base64, data.visemes, () => {
        setStatus({ text: `Ready — ${currentPersonality?.display_name || ''}`.trim() })
      })
    } finally {
      window.clearInterval(keepAliveId)
    }
  }

  async function speakEchoText(text: string, pid: string): Promise<PipelineResponse> {
    const data = await pipelineText({
      text,
      personality_id: pid,
      llm_backend: 'echo',
      session_id: sessionId,
    })
    await playResponse(data)
    return data
  }

  const meme67CacheRef = React.useRef<Map<string, PipelineResponse>>(new Map())

  async function run67MemePhase(pid: string): Promise<void> {
    if (!renderer) return
    // Dramatic beat before the meme begins.
    await new Promise<void>((resolve) => window.setTimeout(resolve, 600))

    // Ensure the audio is ready before we start the 2s spin, so the rotation is continuous.
    let chunk = meme67CacheRef.current.get(pid) || null
    if (!chunk) {
      chunk = await pipelineText({
        text: '67',
        personality_id: pid,
        llm_backend: 'echo',
        session_id: sessionId,
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
  }

  const lastActiveMsRef = React.useRef<number>(performance.now())
  const [dvdMode, setDvdMode] = React.useState(false)
  const ouchRecenterTimeoutRef = React.useRef<number | null>(null)

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

  React.useEffect(() => {
    return () => {
      if (ouchRecenterTimeoutRef.current !== null) {
        window.clearTimeout(ouchRecenterTimeoutRef.current)
        ouchRecenterTimeoutRef.current = null
      }
    }
  }, [])

  React.useEffect(() => {
    const onKey = () => markActive({ recenter: true })
    const onPointer = (e: PointerEvent) => {
      const target = e.target as Element | null
      // Clicking the avatar should not recenter (important for in-place "ouch" animation in DVD mode).
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
      const should = idleFor >= 12_000 && !isProcessing
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

  async function sendText() {
    const msg = text.trim()
    if (!msg || isProcessing) return
    const pid = currentPersonality?.id || 'peter'
    void renderer?.audioPlayer.unlock()

    markActive({ recenter: true })
    setIsProcessing(true)
    setText('')
    addMessage(msg, true)
    setStatus({ text: 'Processing...', className: 'speaking' })

    try {
      if (msg === 'signoface') {
        const p = personalities.find((x) => x.id === 'signoface') || null
        if (p) {
          setCurrentPersonality(p)
          // Ensure it applies immediately (don’t wait for effect) so the face swaps before speaking.
          await renderer?.applyPersonality(p)
        }
        await speakEchoText("It's signing time!", p?.id || pid)
        return
      }

      const slur = detectSlur(msg)
      if (slur) renderer?.setMood('sad')

      let memeRan = false
      if (msg.includes('67')) {
        memeRan = true
        await run67MemePhase(pid)
      }

      const data = await pipelineText({
        text: msg,
        personality_id: pid,
        llm_backend: llmBackend,
        session_id: sessionId,
        safety_hint_language: slur?.language,
      })
      setDebug({
        lang: data.detected_language,
        score: data.detected_language_score,
        voice: data.voice_used,
        enabled: data.language_detection_enabled,
        error: data.language_detection_error ?? null,
      })
      renderer?.setMood(data.mood ?? 'neutral')
      addMessage(data.response_text, false)

      if (!memeRan && data.response_text.includes('67')) {
        memeRan = true
        await run67MemePhase(pid)
      }

      await playResponse(data)
      renderer?.setMood('neutral')
    } catch (e) {
      const err = e instanceof Error ? e.message : String(e)
      setStatus({ text: 'Error: ' + err, className: 'error' })
      addMessage('(Error: ' + err + ')', false)
    } finally {
      setIsProcessing(false)
    }
  }

  async function onRecorded(blob: Blob, mimeType: string) {
    if (isProcessing) return
    const pid = currentPersonality?.id || 'peter'
    markActive({ recenter: true })
    setIsProcessing(true)
    setStatus({ text: 'Transcribing...', className: 'speaking' })

    try {
      const data = await pipelineAudio({ blob, mimeType, personality_id: pid, llm_backend: llmBackend, session_id: sessionId })
      setDebug({
        lang: data.detected_language,
        score: data.detected_language_score,
        voice: data.voice_used,
        enabled: data.language_detection_enabled,
        error: data.language_detection_error ?? null,
      })
      const userText = data.user_text || data.response_text
      addMessage('🎤 ' + userText, true)
      renderer?.setMood(data.mood ?? 'neutral')
      addMessage(data.response_text, false)
      await playResponse(data)
      renderer?.setMood('neutral')
    } catch (e) {
      const err = e instanceof Error ? e.message : String(e)
      setStatus({ text: 'Error: ' + err, className: 'error' })
      addMessage('(Error: ' + err + ')', false)
    } finally {
      setMicHint('')
      setIsProcessing(false)
    }
  }

  const ControlsPanel = () => (
    <div className="section">
      <div className="section-title">LLM</div>
      <LlmBackendToggle value={llmBackend} onChange={setLlmBackend} disabled={isProcessing} />
      <div style={{ height: 14 }} />
      <div className="section-title">Personality</div>
      {/*
        Keep easter-egg personalities selectable programmatically, but hidden from the UI.
      */}
      <PersonalityPicker
        personalities={personalities.filter((p) => p.id !== 'signoface')}
        activeId={currentPersonality?.id || null}
        onSelect={selectPersonality}
        disabled={isProcessing}
      />
    </div>
  )

  return (
    <>
      <div className="grain" />
      <header>
        <div className="logo">
          <a className="logo-link" href="https://ai-avatar.signosoft.com">
            <img src="/logo_full.png" alt="Signosoft" className="logo-img" />
          </a>
        </div>
        <div className="header-subtitle">Avatar demo</div>
      </header>

      {/* Mobile-only chrome (header is hidden on phones via CSS) */}
      <div className="mobile-chrome" aria-hidden={isOptionsOpen ? 'true' : undefined}>
        <a className="logo-link" href="https://ai-avatar.signosoft.com">
          <img src="/logo_full.png" alt="Signosoft" className="mobile-corner-logo" />
        </a>
        <button type="button" className="mobile-options-fab" onClick={() => setIsOptionsOpen(true)} aria-label="Open options">
          Options
        </button>
      </div>

      {isOptionsOpen ? (
        <div className="mobile-sheet-backdrop" role="presentation" onClick={() => setIsOptionsOpen(false)}>
          <div className="mobile-sheet" role="dialog" aria-label="Options" onClick={(e) => e.stopPropagation()}>
            <div className="mobile-sheet-header">
              <div className="mobile-sheet-title">Options</div>
              <button type="button" className="mobile-sheet-close" onClick={() => setIsOptionsOpen(false)} aria-label="Close options">
                ✕
              </button>
            </div>
            <ControlsPanel />
          </div>
        </div>
      ) : null}

      <div className="main-layout">
        <div className={`canvas-area${status.className === 'speaking' ? ' speaking' : ''}`}>
          {[0, 1, 2, 3, 4, 5].map(i => (
            <div key={i} className={`bg-layer bg-layer-${i}${activeBg === i ? ' active' : ''}`} />
          ))}
          <AvatarCanvas
            personality={currentPersonality}
            onRenderer={(r) => {
              setRenderer(r)
              setAssetError(null)
              if (r) {
                r.onError = (msg) => setAssetError(msg)
              }
            }}
            onHud={(t) => setHud(t)}
            onAvatarClick={() => {
              void (async () => {
                if (isProcessing) return
                const dvd = renderer?.getDvdModeEnabled() ?? false
                renderer?.triggerBlackHole({ recenterToCanvas: !dvd })
                const pid = currentPersonality?.id || 'peter'
                // If we were in DVD/pong mode, keep the animation in-place (no recenter snap).
                markActive({ recenter: !dvd })
                setIsProcessing(true)
                setStatus({ text: 'Speaking', className: 'speaking' })
                // After the ouch animation completes, always recenter and reset idle countdown.
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
                  setStatus({ text: `Ready — ${currentPersonality?.display_name || ''}`.trim() })
                }
              })()
            }}
          />
          <div className="avatar-debug">
            <div className="hud" id="hud">
              {assetError ? assetError : hud}
            </div>
            <div className="hud hud-debug">
              <span>
                Lang: {debug.lang || '—'}
                {typeof debug.score === 'number' ? ` (${debug.score.toFixed(2)})` : ''}
              </span>
              <span className="sep">|</span>
              <span>Voice: {debug.voice || '—'}</span>
            </div>
            {debug.enabled === false && debug.error ? <div className="hud hud-debug-note">{debug.error}</div> : null}
          </div>
        </div>

        <div className="sidebar">
          <div className="desktop-controls">
            <ControlsPanel />
          </div>

          <ChatPanel messages={messages} />

          <div className="input-area">
            <div className={'mic-hint' + (micHint ? ' recording' : '')} id="mic-hint">
              {micHint}
            </div>
            <div className="input-row">
              <input
                type="text"
                id="text-input"
                placeholder="Type a message..."
                autoComplete="off"
                value={text}
                disabled={isProcessing}
                onChange={(e) => setText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    void sendText()
                  }
                }}
                onFocus={() => markActive({ recenter: true })}
              />
              <MicButton
                disabled={isProcessing}
                onRecorded={onRecorded}
                onHint={setMicHint}
                onStatus={setStatus}
                onUserGesture={() => {
                  void renderer?.audioPlayer.unlock()
                  markActive({ recenter: true })
                }}
              />
              <button className="send-btn" id="send-btn" disabled={!text.trim() || isProcessing} onClick={() => void sendText()}>
                <svg viewBox="0 0 24 24">
                  <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" />
                </svg>
              </button>
            </div>
          </div>
        </div>
      </div>
    </>
  )
}

export default App
