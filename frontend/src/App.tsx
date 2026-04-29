import * as React from 'react'
import { getPersonalities, pipelineAudio, pipelineText } from './api/client'
import { AvatarCanvas } from './components/AvatarCanvas'
import { ChatPanel, type ChatMessage } from './components/ChatPanel'
import { LlmBackendToggle } from './components/LlmBackendToggle'
import { MicButton } from './components/MicButton'
import { PersonalityPicker } from './components/PersonalityPicker'
import { useLocalStorageState } from './hooks/useLocalStorageState'
import type { LlmBackend, Personality } from './types'
import type { AvatarRenderer } from './rendering/AvatarRenderer'

function App() {
  const [personalities, setPersonalities] = React.useState<Personality[]>([])
  const [currentPersonality, setCurrentPersonality] = React.useState<Personality | null>(null)
  const [renderer, setRenderer] = React.useState<AvatarRenderer | null>(null)
  const [messages, setMessages] = React.useState<ChatMessage[]>([])

  const [llmBackend, setLlmBackend] = useLocalStorageState<LlmBackend>('avatarDemo.llmBackend', 'echo')

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

  async function playResponse(data: { audio_base64: string; visemes: any[] }) {
    if (!data.audio_base64) {
      setStatus({ text: 'Ready (no audio)' })
      return
    }
    if (!renderer) return
    setStatus({ text: 'Speaking', className: 'speaking' })
    await renderer.playTts(data.audio_base64, data.visemes as any, () => {
      setStatus({ text: `Ready — ${currentPersonality?.display_name || ''}`.trim() })
    })
  }

  async function sendText() {
    const msg = text.trim()
    if (!msg || isProcessing) return
    const pid = currentPersonality?.id || 'peter'

    setIsProcessing(true)
    setText('')
    addMessage(msg, true)
    setStatus({ text: 'Processing...', className: 'speaking' })

    try {
      const data = await pipelineText({ text: msg, personality_id: pid, llm_backend: llmBackend })
      setDebug({
        lang: data.detected_language,
        score: data.detected_language_score,
        voice: data.voice_used,
        enabled: data.language_detection_enabled,
        error: data.language_detection_error ?? null,
      })
      addMessage(data.response_text, false)
      await playResponse(data)
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
    setIsProcessing(true)
    setStatus({ text: 'Transcribing...', className: 'speaking' })

    try {
      const data = await pipelineAudio({ blob, mimeType, personality_id: pid, llm_backend: llmBackend })
      setDebug({
        lang: data.detected_language,
        score: data.detected_language_score,
        voice: data.voice_used,
        enabled: data.language_detection_enabled,
        error: data.language_detection_error ?? null,
      })
      const userText = data.user_text || data.response_text
      addMessage('🎤 ' + userText, true)
      addMessage(data.response_text, false)
      await playResponse(data)
    } catch (e) {
      const err = e instanceof Error ? e.message : String(e)
      setStatus({ text: 'Error: ' + err, className: 'error' })
      addMessage('(Error: ' + err + ')', false)
    } finally {
      setMicHint('')
      setIsProcessing(false)
    }
  }

  return (
    <>
      <div className="grain" />
      <header>
        <div className="logo">
          <img src="/assets/logo/logo.png" alt="Signosoft" className="logo-img" />
        </div>
        <div className={'status-badge ' + (status.className || '')} id="status-badge">
          <div className="dot" />
          <span id="status-text">{status.text}</span>
        </div>
      </header>

      <div className="main-layout">
        <div className={'canvas-area' + (status.className === 'speaking' ? ' speaking' : '')}>
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
          />
          <div className="hud" id="hud">
            {assetError ? assetError : hud}
          </div>
          <div className="avatar-debug">
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
          <div className="section">
            <div className="section-title">LLM</div>
            <LlmBackendToggle value={llmBackend} onChange={setLlmBackend} disabled={isProcessing} />
            <div style={{ height: 14 }} />
            <div className="section-title">Personality</div>
            <PersonalityPicker
              personalities={personalities}
              activeId={currentPersonality?.id || null}
              onSelect={selectPersonality}
              disabled={isProcessing}
            />
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
              />
              <MicButton
                disabled={isProcessing}
                onRecorded={onRecorded}
                onHint={setMicHint}
                onStatus={setStatus}
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
