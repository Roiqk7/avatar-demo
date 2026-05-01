import { describe, it, expect, vi } from 'vitest'
import { render } from '@testing-library/react'
import { ChatComposer } from './ChatComposer'

function renderComposer(overrides: Partial<React.ComponentProps<typeof ChatComposer>> = {}) {
  const props: React.ComponentProps<typeof ChatComposer> = {
    text: '',
    onTextChange: vi.fn(),
    onSend: vi.fn(),
    onTextFocus: vi.fn(),
    isProcessing: false,
    micModeOn: false,
    onMicModeChange: vi.fn(),
    micHint: '',
    micNotice: '',
    onMicHint: vi.fn(),
    onMicRecorded: vi.fn(),
    onMicSpeechStart: vi.fn(),
    onMicGesture: vi.fn(),
    onMicStopInterrupt: vi.fn(),
    pipelineStage: null,
    timerStartMs: null,
    ...overrides,
  }

  return render(<ChatComposer {...props} />)
}

describe('ChatComposer (mic hint gating)', () => {
  it('does not render #mic-hint when micModeOn is false (even if micHint is non-empty)', () => {
    const { container } = renderComposer({ micModeOn: false, micHint: 'Listening...' })
    expect(container.querySelector('#mic-hint')).not.toBeInTheDocument()
  })

  it('renders #mic-hint when micModeOn is true', () => {
    const { container } = renderComposer({ micModeOn: true, micHint: 'Listening...' })
    expect(container.querySelector('#mic-hint')).toBeInTheDocument()
  })
})

