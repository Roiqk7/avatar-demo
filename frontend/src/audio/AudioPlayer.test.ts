import { describe, it, expect, vi, beforeEach } from 'vitest'
import { AudioPlayer } from './AudioPlayer'

// Minimal AudioContext mock
function makeCtx(opts: { state?: AudioContextState; decodeRejects?: boolean } = {}) {
  const source = {
    buffer: null as AudioBuffer | null,
    connect: vi.fn(),
    start: vi.fn(),
    stop: vi.fn(),
    onended: null as (() => void) | null,
  }

  const ctx = {
    state: opts.state ?? 'running',
    resume: vi.fn().mockResolvedValue(undefined),
    createBufferSource: vi.fn(() => source),
    createGain: vi.fn(() => ({ gain: { value: 1 }, connect: vi.fn(), disconnect: vi.fn() })),
    destination: {},
    decodeAudioData: opts.decodeRejects
      ? vi.fn().mockRejectedValue(new Error('decode failed'))
      : vi.fn().mockResolvedValue({} as AudioBuffer),
  }

  return { ctx, source }
}

// Tiny valid base64 WAV (44-byte header, all zeros) — enough to pass atob
const VALID_B64 = btoa('\x00'.repeat(44))

describe('AudioPlayer', () => {
  let player: AudioPlayer

  beforeEach(() => {
    player = new AudioPlayer()
  })

  it('play() with empty base64 calls onEnd immediately', async () => {
    const onEnd = vi.fn()
    await player.play('', onEnd)
    expect(onEnd).toHaveBeenCalledOnce()
  })

  it('stop() when no audio is playing does not throw', () => {
    expect(() => player.stop()).not.toThrow()
  })

  it('play() with invalid base64 calls onError with an Error', async () => {
    const { ctx } = makeCtx()
    player._ctx = ctx as unknown as AudioContext

    const onEnd = vi.fn()
    const onError = vi.fn()
    await player.play('!!!not-base64!!!', onEnd, onError)

    expect(onError).toHaveBeenCalledOnce()
    expect(onError.mock.calls[0][0]).toBeInstanceOf(Error)
  })

  it('play() with invalid base64 still calls onEnd (state machine must not hang)', async () => {
    const { ctx } = makeCtx()
    player._ctx = ctx as unknown as AudioContext

    const onEnd = vi.fn()
    await player.play('!!!not-base64!!!', onEnd)

    expect(onEnd).toHaveBeenCalledOnce()
  })

  it('play() when decodeAudioData rejects calls onError', async () => {
    const { ctx } = makeCtx({ decodeRejects: true })
    player._ctx = ctx as unknown as AudioContext

    const onError = vi.fn()
    const onEnd = vi.fn()
    await player.play(VALID_B64, onEnd, onError)

    expect(onError).toHaveBeenCalledOnce()
    expect(onError.mock.calls[0][0]).toBeInstanceOf(Error)
    // onEnd must still fire
    expect(onEnd).toHaveBeenCalledOnce()
  })

  it('play() with suspended AudioContext calls onError', async () => {
    const { ctx } = makeCtx({ state: 'suspended' })
    player._ctx = ctx as unknown as AudioContext

    const onError = vi.fn()
    await player.play(VALID_B64, undefined, onError)

    expect(onError).toHaveBeenCalledOnce()
  })
})
