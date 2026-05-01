import type { ChatTurn, LlmBackend, Personality, PipelineResponse } from '../types'

export type PipelineAudioStreamEvent =
  | { type: 'stt'; user_text: string }
  | { type: 'delta'; delta: string }
  | { type: 'audio'; seq: number; audio_base64: string; visemes: PipelineResponse['visemes']; duration_ms: number }
  | { type: 'done'; data: PipelineResponse }
  | { type: 'error'; message: string }

export async function getPersonalities(): Promise<Personality[]> {
  const res = await fetch('/api/personalities')
  if (!res.ok) throw new Error(await res.text())
  return (await res.json()) as Personality[]
}

export async function pipelineText(args: {
  text: string
  personality_id: string
  llm_backend: LlmBackend
  session_id: string
  history: ChatTurn[]
  safety_hint_language?: 'en' | 'cs'
  signal?: AbortSignal
}): Promise<PipelineResponse> {
  const { signal, ...payload } = args
  const res = await fetch('/api/pipeline/text', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal,
  })
  if (!res.ok) throw new Error(await res.text())
  return (await res.json()) as PipelineResponse
}

export type PipelineTextStreamEvent =
  | { type: 'delta'; delta: string }
  | { type: 'audio'; seq: number; audio_base64: string; visemes: PipelineResponse['visemes']; duration_ms: number }
  | { type: 'done'; data: PipelineResponse }
  | { type: 'error'; message: string }

export async function* pipelineTextStream(args: {
  text: string
  personality_id: string
  llm_backend: LlmBackend
  session_id: string
  history: ChatTurn[]
  safety_hint_language?: 'en' | 'cs'
  signal?: AbortSignal
}): AsyncGenerator<PipelineTextStreamEvent, void, void> {
  const { signal, ...payload } = args
  const res = await fetch('/api/pipeline/text_stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal,
  })
  if (!res.ok || !res.body) {
    yield { type: 'error', message: 'Something went wrong. Please try again.' }
    return
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''

  const emit = (eventName: string, data: string): PipelineTextStreamEvent | null => {
    if (eventName === 'delta') {
      try {
        const obj = JSON.parse(data) as { delta?: unknown }
        const d = typeof obj.delta === 'string' ? obj.delta : ''
        return d ? { type: 'delta', delta: d } : null
      } catch {
        return null
      }
    }
    if (eventName === 'audio') {
      try {
        const obj = JSON.parse(data) as { seq?: unknown; audio_base64?: unknown; visemes?: unknown; duration_ms?: unknown }
        const seq = typeof obj.seq === 'number' ? obj.seq : 0
        const audio_base64 = typeof obj.audio_base64 === 'string' ? obj.audio_base64 : ''
        const visemes = Array.isArray(obj.visemes) ? (obj.visemes as PipelineResponse['visemes']) : []
        const duration_ms = typeof obj.duration_ms === 'number' ? obj.duration_ms : 0
        return audio_base64 ? { type: 'audio', seq, audio_base64, visemes, duration_ms } : null
      } catch {
        return null
      }
    }
    if (eventName === 'done') {
      try {
        const obj = JSON.parse(data) as PipelineResponse
        return { type: 'done', data: obj }
      } catch {
        return null
      }
    }
    if (eventName === 'error') {
      try {
        const obj = JSON.parse(data) as { message?: unknown }
        return { type: 'error', message: typeof obj.message === 'string' ? obj.message : 'Something went wrong.' }
      } catch {
        return { type: 'error', message: 'Something went wrong. Please try again.' }
      }
    }
    return null
  }

  let curEvent = ''
  let curData = ''

  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })

    while (true) {
      const idx = buf.indexOf('\n')
      if (idx < 0) break
      const line = buf.slice(0, idx)
      buf = buf.slice(idx + 1)

      const trimmed = line.replace(/\r$/, '')
      if (!trimmed) {
        const evt = emit(curEvent, curData)
        if (evt) yield evt
        curEvent = ''
        curData = ''
        continue
      }
      if (trimmed.startsWith('event:')) {
        curEvent = trimmed.slice('event:'.length).trim()
        continue
      }
      if (trimmed.startsWith('data:')) {
        const chunk = trimmed.slice('data:'.length).trim()
        curData = curData ? curData + '\n' + chunk : chunk
      }
    }
  }

  try {
    reader.releaseLock()
  } catch {
    // ignore
  }
}

export async function pipelineAudio(args: {
  blob: Blob
  mimeType: string
  personality_id: string
  llm_backend: LlmBackend
  session_id: string
  history: ChatTurn[]
  interaction_mode?: 'listening'
  signal?: AbortSignal
}): Promise<PipelineResponse> {
  const formData = new FormData()
  const ext = getExtFromMime(args.mimeType)
  formData.append('audio_file', args.blob, `recording.${ext}`)
  formData.append('personality_id', args.personality_id)
  formData.append('llm_backend', args.llm_backend)
  formData.append('session_id', args.session_id)
  formData.append('history', JSON.stringify(args.history ?? []))
  if (args.interaction_mode) formData.append('interaction_mode', args.interaction_mode)

  const res = await fetch('/api/pipeline/audio', { method: 'POST', body: formData, signal: args.signal })
  if (!res.ok) throw new Error(await res.text())
  return (await res.json()) as PipelineResponse
}

export async function* pipelineAudioStream(args: {
  blob: Blob
  mimeType: string
  personality_id: string
  llm_backend: LlmBackend
  session_id: string
  history: ChatTurn[]
  interaction_mode?: 'listening'
  signal?: AbortSignal
}): AsyncGenerator<PipelineAudioStreamEvent, void, void> {
  const formData = new FormData()
  const ext = getExtFromMime(args.mimeType)
  formData.append('audio_file', args.blob, `recording.${ext}`)
  formData.append('personality_id', args.personality_id)
  formData.append('llm_backend', args.llm_backend)
  formData.append('session_id', args.session_id)
  formData.append('history', JSON.stringify(args.history ?? []))
  if (args.interaction_mode) formData.append('interaction_mode', args.interaction_mode)

  const res = await fetch('/api/pipeline/audio_stream', { method: 'POST', body: formData, signal: args.signal })
  if (!res.ok || !res.body) {
    yield { type: 'error', message: 'Something went wrong. Please try again.' }
    return
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''

  const emit = (eventName: string, data: string): PipelineAudioStreamEvent | null => {
    if (eventName === 'stt') {
      try {
        const obj = JSON.parse(data) as { user_text?: unknown }
        return { type: 'stt', user_text: typeof obj.user_text === 'string' ? obj.user_text : '' }
      } catch {
        return null
      }
    }
    if (eventName === 'delta') {
      try {
        const obj = JSON.parse(data) as { delta?: unknown }
        const d = typeof obj.delta === 'string' ? obj.delta : ''
        return d ? { type: 'delta', delta: d } : null
      } catch {
        return null
      }
    }
    if (eventName === 'audio') {
      try {
        const obj = JSON.parse(data) as { seq?: unknown; audio_base64?: unknown; visemes?: unknown; duration_ms?: unknown }
        const seq = typeof obj.seq === 'number' ? obj.seq : 0
        const audio_base64 = typeof obj.audio_base64 === 'string' ? obj.audio_base64 : ''
        const visemes = Array.isArray(obj.visemes) ? (obj.visemes as PipelineResponse['visemes']) : []
        const duration_ms = typeof obj.duration_ms === 'number' ? obj.duration_ms : 0
        return audio_base64 ? { type: 'audio', seq, audio_base64, visemes, duration_ms } : null
      } catch {
        return null
      }
    }
    if (eventName === 'done') {
      try {
        const obj = JSON.parse(data) as PipelineResponse
        return { type: 'done', data: obj }
      } catch {
        return null
      }
    }
    if (eventName === 'error') {
      try {
        const obj = JSON.parse(data) as { message?: unknown }
        return { type: 'error', message: typeof obj.message === 'string' ? obj.message : 'Something went wrong.' }
      } catch {
        return { type: 'error', message: 'Something went wrong. Please try again.' }
      }
    }
    return null
  }

  let curEvent = ''
  let curData = ''

  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })

    while (true) {
      const idx = buf.indexOf('\n')
      if (idx < 0) break
      const line = buf.slice(0, idx)
      buf = buf.slice(idx + 1)

      const trimmed = line.replace(/\r$/, '')
      if (!trimmed) {
        const evt = emit(curEvent, curData)
        if (evt) yield evt
        curEvent = ''
        curData = ''
        continue
      }
      if (trimmed.startsWith('event:')) {
        curEvent = trimmed.slice('event:'.length).trim()
        continue
      }
      if (trimmed.startsWith('data:')) {
        const chunk = trimmed.slice('data:'.length).trim()
        curData = curData ? curData + '\n' + chunk : chunk
      }
    }
  }

  try {
    reader.releaseLock()
  } catch {
    // ignore
  }
}

function getExtFromMime(mime: string): string {
  if (mime.includes('mp4')) return 'm4a'  // audio/mp4 and audio/mp4;codecs=aac → .m4a (OpenAI accepts)
  if (mime.includes('webm')) return 'webm'
  if (mime.includes('ogg')) return 'ogg'
  if (mime.includes('wav')) return 'wav'
  return 'webm'
}

