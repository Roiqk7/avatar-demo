import type { LlmBackend, Personality, PipelineResponse } from '../types'

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

export async function pipelineAudio(args: {
  blob: Blob
  mimeType: string
  personality_id: string
  llm_backend: LlmBackend
  session_id: string
  interaction_mode?: 'listening'
  signal?: AbortSignal
}): Promise<PipelineResponse> {
  const formData = new FormData()
  const ext = getExtFromMime(args.mimeType)
  formData.append('audio_file', args.blob, `recording.${ext}`)
  formData.append('personality_id', args.personality_id)
  formData.append('llm_backend', args.llm_backend)
  formData.append('session_id', args.session_id)
  if (args.interaction_mode) formData.append('interaction_mode', args.interaction_mode)

  const res = await fetch('/api/pipeline/audio', { method: 'POST', body: formData, signal: args.signal })
  if (!res.ok) throw new Error(await res.text())
  return (await res.json()) as PipelineResponse
}

function getExtFromMime(mime: string): string {
  if (mime.includes('webm')) return 'webm'
  if (mime.includes('ogg')) return 'ogg'
  if (mime.includes('wav')) return 'wav'
  return 'webm'
}

