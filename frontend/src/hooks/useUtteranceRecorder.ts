import * as React from 'react'

// Prefer compressed formats. Safari supports AAC in mp4; Chrome/Firefox support Opus in webm.
// audioBitsPerSecond: 32_000 limits to ~32kbps, reducing payload size ~75% vs. default for speech.
const MIME_TYPE_PREFERENCES = [
  'audio/mp4;codecs=aac',
  'audio/mp4',
  'audio/webm;codecs=opus',
  'audio/webm',
  'audio/ogg;codecs=opus',
  'audio/ogg',
  'audio/wav',
]

const AUDIO_BITS_PER_SECOND = 32_000

const MIN_BLOB_BYTES = 1000

type Callbacks = {
  onUtterance: (blob: Blob, mimeType: string) => void
  onTooSmall?: () => void
}

function pickMimeType(): string {
  for (const t of MIME_TYPE_PREFERENCES) {
    if (typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported(t)) return t
  }
  return ''
}

/**
 * Records mic audio between explicit start/stop. Emits a single Blob per utterance.
 * Independent of VAD — caller decides start/stop boundaries.
 */
export function useUtteranceRecorder(callbacks: Callbacks): {
  start: (stream: MediaStream) => void
  stop: () => void
  dispose: () => void
} {
  const recorderRef = React.useRef<MediaRecorder | null>(null)
  const chunksRef = React.useRef<Blob[]>([])
  const cbRef = React.useRef(callbacks)
  React.useLayoutEffect(() => {
    cbRef.current = callbacks
  })

  const stop = React.useCallback(() => {
    const mr = recorderRef.current
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

  const dispose = React.useCallback(() => {
    stop()
    recorderRef.current = null
    chunksRef.current = []
  }, [stop])

  const start = React.useCallback((stream: MediaStream) => {
    if (recorderRef.current && recorderRef.current.state !== 'inactive') return
    const mimeType = pickMimeType()
    if (!mimeType) return
    chunksRef.current = []

    const mr = new MediaRecorder(stream, { mimeType, audioBitsPerSecond: AUDIO_BITS_PER_SECOND })
    mr.ondataavailable = (e) => {
      if (e.data.size > 0) chunksRef.current.push(e.data)
    }
    mr.onstop = () => {
      const chunks = chunksRef.current
      chunksRef.current = []
      recorderRef.current = null
      if (!chunks.length) return
      const blob = new Blob(chunks, { type: mimeType })
      if (blob.size < MIN_BLOB_BYTES) {
        cbRef.current.onTooSmall?.()
        return
      }
      cbRef.current.onUtterance(blob, mimeType)
    }
    recorderRef.current = mr
    mr.start(250)
  }, [])

  React.useEffect(() => () => dispose(), [dispose])

  return { start, stop, dispose }
}
