import * as React from 'react'

export type ChatMessage = {
  id: string
  label: string
  text: string
  isUser: boolean
}

export function ChatPanel(props: { messages: ChatMessage[] }) {
  const { messages } = props
  const bottomRef = React.useRef<HTMLDivElement | null>(null)
  const [copiedId, setCopiedId] = React.useState<string | null>(null)
  const copiedTimerRef = React.useRef<number | null>(null)

  React.useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: 'end' })
  }, [messages.length])

  React.useEffect(() => {
    return () => {
      if (copiedTimerRef.current) window.clearTimeout(copiedTimerRef.current)
    }
  }, [])

  async function copyToClipboard(text: string) {
    const normalized = text.trim()
    if (!normalized) return

    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(normalized)
      return
    }

    // Fallback for older browsers / non-secure contexts.
    const ta = document.createElement('textarea')
    ta.value = normalized
    ta.setAttribute('readonly', 'true')
    ta.style.position = 'fixed'
    ta.style.top = '-1000px'
    ta.style.left = '-1000px'
    document.body.appendChild(ta)
    ta.select()
    document.execCommand('copy')
    document.body.removeChild(ta)
  }

  return (
    <div className="response-area" id="response-area">
      {messages.map((m) => (
        <div key={m.id} className={'response-bubble' + (m.isUser ? ' user' : '')}>
          <div className="msg-actions">
            <button
              type="button"
              className={'copy-btn' + (copiedId === m.id ? ' copied' : '')}
              aria-label={copiedId === m.id ? 'Copied' : 'Copy message'}
              title={copiedId === m.id ? 'Copied' : 'Copy'}
              onClick={() => {
                void (async () => {
                  try {
                    await copyToClipboard(m.text)
                    setCopiedId(m.id)
                    if (copiedTimerRef.current) window.clearTimeout(copiedTimerRef.current)
                    copiedTimerRef.current = window.setTimeout(() => setCopiedId((cur) => (cur === m.id ? null : cur)), 1200)
                  } catch {
                    // ignore
                  }
                })()
              }}
            >
              <span className="copy-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24">
                  <path d="M16 1H6a2 2 0 0 0-2 2v12h2V3h10V1zm3 4H10a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h9a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2zm0 16H10V7h9v14z" />
                </svg>
              </span>
              <span className="copy-text">{copiedId === m.id ? 'Copied' : 'Copy'}</span>
            </button>
          </div>
          <div className="label">{m.label}</div>
          {m.text}
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  )
}

