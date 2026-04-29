import type { LlmBackend } from '../types'

export function LlmBackendToggle(props: {
  value: LlmBackend
  onChange: (v: LlmBackend) => void
  disabled?: boolean
}) {
  const { value, onChange, disabled } = props
  return (
    <div className="toggle" aria-label="LLM backend toggle">
      <button
        type="button"
        className={value === 'echo' ? 'active' : ''}
        onClick={() => onChange('echo')}
        disabled={disabled}
        title="Echo repeats input (no API cost)"
      >
        Echo
      </button>
      <button
        type="button"
        className={value === 'openai' ? 'active' : ''}
        onClick={() => onChange('openai')}
        disabled={disabled}
        title="OpenAI Chat Completions"
      >
        OpenAI
      </button>
    </div>
  )
}

