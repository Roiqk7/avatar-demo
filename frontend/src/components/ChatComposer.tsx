import * as React from 'react'
import { MicButton } from './MicButton'
import { MicHintBar } from './MicHintBar'
import { WaveformVisualizer } from './WaveformVisualizer'

type PipelineStage = 'stt' | 'llm' | 'speaking' | null

type Props = {
  text: string
  onTextChange: (value: string) => void
  onSend: () => void
  onTextFocus: () => void
  isProcessing: boolean
  micModeOn: boolean
  onMicModeChange: (on: boolean) => void
  micHint: string
  micNotice?: string
  onMicHint: (hint: string) => void
  onMicRecorded: (blob: Blob, mimeType: string) => Promise<void> | void
  onMicSpeechStart: () => void
  onMicGesture: () => void
  onMicStopInterrupt: () => void
  pipelineStage?: PipelineStage
  timerStartMs?: number | null
}

export function ChatComposer(props: Props) {
  const [isListening, setIsListening] = React.useState(false)
  const samplesRef = React.useRef<Float32Array>(new Float32Array(1024))

  const handleAudioFrame = React.useCallback((samples: Float32Array) => {
    samplesRef.current = samples
  }, [])

  const showMicHint =
    props.micModeOn || Boolean(props.pipelineStage) || Boolean((props.micNotice || '').trim())

  return (
    <div className="input-area">
      {showMicHint ? (
        <MicHintBar
          state={'IDLE_LISTENING'}
          hint={props.micHint}
          notice={props.micNotice}
          liveTranscript=""
          pipelineStage={props.pipelineStage}
          timerStartMs={props.timerStartMs}
        />
      ) : null}
      <div className="input-row">
        <div className="input-field-slot">
          <input
            type="text"
            id="text-input"
            className={isListening ? 'hidden-layer' : 'visible-layer'}
            placeholder="Type a message..."
            autoComplete="off"
            value={props.text}
            disabled={props.isProcessing || isListening}
            onChange={(e) => props.onTextChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                props.onSend()
              }
            }}
            onFocus={props.onTextFocus}
          />
          <div className={`waveform-wrapper ${isListening ? 'visible-layer' : 'hidden-layer'}`}>
            <WaveformVisualizer samplesRef={samplesRef} isActive={isListening} />
          </div>
        </div>
        <MicButton
          disabled={props.isProcessing}
          onRecorded={props.onMicRecorded}
          onHint={props.onMicHint}
          onSpeechStart={props.onMicSpeechStart}
          onUserGesture={props.onMicGesture}
          onStopInterrupt={props.onMicStopInterrupt}
          onListeningChange={(on) => {
            setIsListening(on)
            props.onMicModeChange(on)
          }}
          onAudioFrame={handleAudioFrame}
        />
        <button
          className="send-btn"
          id="send-btn"
          disabled={!props.text.trim() || props.isProcessing}
          onClick={props.onSend}
        >
          <svg viewBox="0 0 24 24">
            <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" />
          </svg>
        </button>
      </div>
    </div>
  )
}
