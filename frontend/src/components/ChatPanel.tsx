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

  React.useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: 'end' })
  }, [messages.length])

  return (
    <div className="response-area" id="response-area">
      {messages.map((m) => (
        <div key={m.id} className={'response-bubble' + (m.isUser ? ' user' : '')}>
          <div className="label">{m.label}</div>
          {m.text}
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  )
}

