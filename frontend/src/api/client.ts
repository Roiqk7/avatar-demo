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
}): Promise<PipelineResponse> {
  const res = await fetch('/api/pipeline/text', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(args),
  })
  if (!res.ok) throw new Error(await res.text())
  return (await res.json()) as PipelineResponse
}

export async function pipelineAudio(args: {
  blob: Blob
  mimeType: string
  personality_id: string
  llm_backend: LlmBackend
}): Promise<PipelineResponse> {
  const formData = new FormData()
  const ext = getExtFromMime(args.mimeType)
  formData.append('audio_file', args.blob, `recording.${ext}`)
  formData.append('personality_id', args.personality_id)
  formData.append('llm_backend', args.llm_backend)

  const res = await fetch('/api/pipeline/audio', { method: 'POST', body: formData })
  if (!res.ok) throw new Error(await res.text())
  return (await res.json()) as PipelineResponse
}

function getExtFromMime(mime: string): string {
  if (mime.includes('webm')) return 'webm'
  if (mime.includes('ogg')) return 'ogg'
  if (mime.includes('wav')) return 'wav'
  return 'webm'
}

