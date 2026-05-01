import { AvatarCanvas } from './AvatarCanvas'
import type { Personality } from '../types'
import type { AvatarRenderer } from '../rendering/AvatarRenderer'

type DebugInfo = {
  lang?: string | null
  score?: number | null
  lang_mode?: string | null
  session_lang?: string | null
  voice?: string | null
  voice_mode?: string | null
  stt?: string | null
  llm?: string | null
  tts?: string | null
  detector?: string | null
  timing_stt_ms?: number | null
  timing_llm_ms?: number | null
  timing_tts_ms?: number | null
}

type Props = {
  personality: Personality | null
  isSpeakingClass: boolean
  activeBg: number
  hud: string
  debug: DebugInfo
  onRenderer: (r: AvatarRenderer | null) => void
  onHud: (text: string) => void
  onAvatarClick: () => void
}

function fmtMs(ms: number | null | undefined): string {
  if (typeof ms !== 'number') return '—'
  return `${(ms / 1000).toFixed(1)}s`
}

export function AvatarStage(props: Props) {
  return (
    <div className={`canvas-area${props.isSpeakingClass ? ' speaking' : ''}`}>
      {[0, 1, 2, 3, 4, 5].map((i) => (
        <div key={i} className={`bg-layer bg-layer-${i}${props.activeBg === i ? ' active' : ''}`} />
      ))}
      <AvatarCanvas
        personality={props.personality}
        onRenderer={props.onRenderer}
        onHud={props.onHud}
        onAvatarClick={props.onAvatarClick}
      />
      <div className="avatar-debug">
        <div className="hud" id="hud">{props.hud}</div>
        <div className="hud hud-debug">
          <span>
            Lang: {props.debug.lang || '—'}
            {typeof props.debug.score === 'number' ? ` (${props.debug.score.toFixed(2)})` : ''}
            {props.debug.lang_mode ? ` [${props.debug.lang_mode}]` : ''}
          </span>
          <span className="sep">|</span>
          <span>
            Voice: {props.debug.voice || '—'}
            {props.debug.voice_mode ? ` [${props.debug.voice_mode}]` : ''}
          </span>
          <span className="sep">|</span>
          <span>SessionLang: {props.debug.session_lang || '—'}</span>
        </div>
        <div className="hud hud-debug">
          <span>STT: {props.debug.stt || '—'}</span>
          <span className="sep">|</span>
          <span>LLM: {props.debug.llm || '—'}</span>
          <span className="sep">|</span>
          <span>TTS: {props.debug.tts || '—'}</span>
          <span className="sep">|</span>
          <span>Detector: {props.debug.detector || '—'}</span>
        </div>
        <div className="hud hud-debug">
          <span>STT: {fmtMs(props.debug.timing_stt_ms)}</span>
          <span className="sep">|</span>
          <span>LLM: {fmtMs(props.debug.timing_llm_ms)}</span>
          <span className="sep">|</span>
          <span>TTS: {fmtMs(props.debug.timing_tts_ms)}</span>
        </div>
      </div>
    </div>
  )
}
