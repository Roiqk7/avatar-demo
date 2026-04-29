import * as React from 'react'

function getMimeType(): string {
  const types = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/ogg', 'audio/wav']
  for (const t of types) {
    if ((window as any).MediaRecorder?.isTypeSupported?.(t)) return t
  }
  return ''
}

export function MicButton(props: {
  disabled?: boolean
  onRecorded: (blob: Blob, mimeType: string) => Promise<void> | void
  onHint?: (hint: string) => void
  onStatus?: (status: { text: string; className?: string }) => void
}) {
  const { disabled, onRecorded, onHint, onStatus } = props
  const [isRecording, setIsRecording] = React.useState(false)
  const mediaRecorderRef = React.useRef<MediaRecorder | null>(null)
  const streamRef = React.useRef<MediaStream | null>(null)
  const chunksRef = React.useRef<Blob[]>([])

  const stopStream = React.useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null
  }, [])

  React.useEffect(() => () => stopStream(), [stopStream])

  async function startRecording() {
    if (disabled || isRecording) return
    let stream: MediaStream
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    } catch (e) {
      console.error('Mic access denied:', e)
      onStatus?.({ text: 'Microphone access denied', className: 'error' })
      onHint?.('Mic access denied — check browser permissions')
      return
    }

    const mimeType = getMimeType()
    if (!mimeType) {
      onStatus?.({ text: 'No supported audio format', className: 'error' })
      stream.getTracks().forEach((t) => t.stop())
      return
    }

    streamRef.current = stream
    chunksRef.current = []
    const mr = new MediaRecorder(stream, { mimeType })
    mediaRecorderRef.current = mr

    mr.ondataavailable = (e) => {
      if (e.data.size > 0) chunksRef.current.push(e.data)
    }

    mr.onstop = async () => {
      stopStream()
      const chunks = chunksRef.current
      chunksRef.current = []
      if (!chunks.length) return

      const blob = new Blob(chunks, { type: mimeType })
      if (blob.size < 1000) {
        onHint?.('')
        onStatus?.({ text: 'Recording too short — try again' })
        return
      }
      await onRecorded(blob, mimeType)
    }

    mr.start(250)
    setIsRecording(true)
    onStatus?.({ text: 'Recording...', className: 'speaking' })

    const recStart = Date.now()
    const timer = window.setInterval(() => {
      if (!mr || mr.state === 'inactive') {
        window.clearInterval(timer)
        return
      }
      const sec = ((Date.now() - recStart) / 1000).toFixed(1)
      onHint?.(`Recording... ${sec}s — click mic to stop`)
    }, 100)
    onHint?.('Recording... 0.0s — click mic to stop')
  }

  function stopRecording() {
    const mr = mediaRecorderRef.current
    if (!mr || !isRecording) return
    setIsRecording(false)
    onHint?.('Processing speech...')
    if (mr.state !== 'inactive') mr.stop()
  }

  const hasSupport =
    typeof navigator !== 'undefined' &&
    !!navigator.mediaDevices &&
    typeof navigator.mediaDevices.getUserMedia === 'function' &&
    typeof (window as any).MediaRecorder !== 'undefined'

  return (
    <button
      className={'mic-btn' + (isRecording ? ' recording' : '')}
      id="mic-btn"
      type="button"
      title={hasSupport ? 'Click to record, click again to stop' : 'Microphone not supported in this browser'}
      disabled={disabled || !hasSupport}
      onClick={() => (isRecording ? stopRecording() : void startRecording())}
    >
      <svg className="mic-icon" viewBox="0 0 24 24">
        <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm-1-9c0-.55.45-1 1-1s1 .45 1 1v6c0 .55-.45 1-1 1s-1-.45-1-1V5z" />
        <path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z" />
      </svg>
      <svg className="stop-icon" viewBox="0 0 24 24" style={{ display: isRecording ? 'block' : 'none' }}>
        <rect x="6" y="6" width="12" height="12" rx="2" />
      </svg>
    </button>
  )
}

