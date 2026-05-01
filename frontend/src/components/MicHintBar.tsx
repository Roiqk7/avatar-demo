import * as React from 'react'
import type { InteractiveState } from '../state/interactiveMachine'

type PipelineStage = 'stt' | 'llm' | 'speaking' | null

type Props = {
  state: InteractiveState
  hint: string
  notice?: string
  liveTranscript: string
  pipelineStage?: PipelineStage
  timerStartMs?: number | null
}

const STAGE_LABELS: Record<NonNullable<PipelineStage>, string> = {
  stt: 'Processing speech',
  llm: 'Thinking of response',
  speaking: 'Speaking…',
}

/**
 * Status bar above the mic button.
 * - Shows live elapsed time while STT or LLM stages are active.
 * - Falls back to state-driven hint text when no pipeline stage is active.
 * - notice always takes priority (error/warning messages).
 */
export function MicHintBar({ state, hint, notice, liveTranscript, pipelineStage, timerStartMs }: Props) {
  const [elapsed, setElapsed] = React.useState(0)

  React.useEffect(() => {
    if (!timerStartMs) {
      setElapsed(0)
      return
    }
    setElapsed(Date.now() - timerStartMs)
    const id = window.setInterval(() => {
      setElapsed(Date.now() - timerStartMs)
    }, 100)
    return () => window.clearInterval(id)
  }, [timerStartMs])

  const isOn = state !== 'OFF'
  const showTranscript = state === 'USER_SPEAKING' && liveTranscript.length > 0
  const className = ['mic-hint', isOn ? 'recording' : '', showTranscript ? 'with-transcript' : '']
    .filter(Boolean)
    .join(' ')

  let displayText: string
  const noticeText = (notice || '').trim()
  if (noticeText) {
    displayText = noticeText
  } else if (pipelineStage === 'stt' && timerStartMs) {
    displayText = `${STAGE_LABELS.stt} ${(elapsed / 1000).toFixed(1)}s`
  } else if (pipelineStage === 'llm' && timerStartMs) {
    displayText = `${STAGE_LABELS.llm} ${(elapsed / 1000).toFixed(1)}s`
  } else if (pipelineStage === 'speaking') {
    displayText = STAGE_LABELS.speaking
  } else {
    displayText = isOn ? hint : ''
  }

  return (
    <div className={className} id="mic-hint">
      {showTranscript ? <div className="mic-transcript">{liveTranscript}</div> : null}
      <div className="mic-hint-text">{displayText}</div>
    </div>
  )
}
