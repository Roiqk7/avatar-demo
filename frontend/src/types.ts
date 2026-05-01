export type LlmBackend = 'echo' | 'openai' | 'max'

export type ChatTurn = { role: 'user' | 'assistant'; content: string }

export type VisemeOut = {
  id: number
  offset_ms: number
}

export type PipelineResponse = {
  user_text: string
  response_text: string
  audio_base64: string
  visemes: VisemeOut[]
  duration_ms: number
  mood?: 'neutral' | 'sad'
  safety_triggered?: boolean
  safety_language?: 'en' | 'cs' | null
  detected_language?: string | null
  detected_language_score?: number | null
  debug_lang_mode?: string | null
  debug_session_lang?: string | null
  voice_used?: string | null
  debug_voice_mode?: string | null
  language_detection_enabled?: boolean
  language_detection_error?: string | null
  debug_stt_model?: string | null
  debug_stt_language?: string | null
  debug_llm_backend?: string | null
  debug_llm_model?: string | null
  debug_tts_backend?: string | null
  debug_lang_detect_backend?: string | null
  timing_stt_ms?: number | null
  timing_llm_ms?: number | null
  timing_tts_ms?: number | null
}

export type Personality = {
  id: string
  display_name: string
  window_title: string
  face_layout: {
    mouth_width_ratio: number
    mouth_height_ratio: number
    mouth_y_ratio: number
    eye_y_ratio: number
    eye_width_ratio: number
    eye_height_ratio: number
  }
  assets: {
    face_path: string
    visemes_dir: string
    eyes_dir: string
  }
  viseme_labels: string[]
  idle_mouth_pools: {
    subtle: string[]
    happy: string[]
    goofy: string[]
    dramatic: string[]
  }
  idle_mouth_names: string[]
  mouth_idle_enabled: boolean
  eye_config: {
    enable_micro_glance: boolean
    enable_long_glance: boolean
    enable_expr_glance: boolean
    enable_goofy_sequences: boolean
    blink_initial_ms: [number, number]
    blink_after_ms: [number, number]
    micro_initial_ms: [number, number]
    micro_after_ms: [number, number]
    micro_glance_indices: number[]
    micro_return_ms: [number, number]
    glance_initial_ms: [number, number]
    glance_after_ms: [number, number]
    glance_indices: number[]
    glance_return_ms: [number, number]
    expr_initial_ms: [number, number]
    expr_after_ms: [number, number]
    expr_indices: number[]
    expr_return_ms: [number, number]
    goofy_initial_ms: [number, number]
    goofy_after_ms: [number, number]
    micro_transition_ms: number
    glance_transition_ms: number
    expr_transition_ms: number
    forbidden_eye_indices: number[]
  }
  mouth_timing: {
    idle_delay_ms: number
    subtle_next_initial: [number, number]
    subtle_next_after: [number, number]
    happy_next_initial: [number, number]
    happy_next_after: [number, number]
    goofy_next_initial: [number, number]
    goofy_next_after: [number, number]
    dramatic_next_initial: [number, number]
    dramatic_next_after: [number, number]
    subtle_transition_ms: number
    subtle_hold_ms: [number, number]
    happy_transition_ms: number
    happy_hold_ms: [number, number]
    goofy_transition_ms: number
    goofy_hold_ms: [number, number]
    dramatic_transition_ms: number
    dramatic_hold_ms: [number, number]
    return_transition_ms: number
  }
  emotes: Array<{
    name: string
    eye_seq: Array<[number, number, number]>
    mouth: string
    mouth_hold_ms: number
  }>
  emote_timing: {
    enabled: boolean
    idle_delay_ms: number
    first_emote_after_ms: [number, number]
    emote_after_ms: [number, number]
  }
}

