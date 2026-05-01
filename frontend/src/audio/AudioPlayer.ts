export class AudioPlayer {
  _ctx: AudioContext | null = null
  _source: AudioBufferSourceNode | null = null
  _scheduled: AudioBufferSourceNode[] = []
  _nextStartTime: number | null = null
  _htmlAudio: HTMLAudioElement | null = null

  _ensureCtx() {
    const CtxCtor =
      window.AudioContext ||
      (window as Window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
    if (!this._ctx) this._ctx = new CtxCtor()
  }

  async unlock(): Promise<void> {
    this._ensureCtx()
    if (!this._ctx) return
    if (this._ctx.state === 'suspended') {
      try {
        await this._ctx.resume()
      } catch (e) {
        console.warn('AudioContext resume failed:', e)
      }
    }
  }

  async play(
    base64Wav: string,
    onEnd?: () => void,
    onError?: (err: Error) => void,
    onStart?: (startTimeMs: number) => void,
  ): Promise<void> {
    return await new Promise<void>((resolve) => {
      const finish = () => {
        onEnd?.()
        resolve()
      }

      const fail = (err: Error) => {
        onError?.(err)
        finish()
      }

      if (!base64Wav) {
        finish()
        return
      }

      void (async () => {
        await this.unlock()
        // If WebAudio can't start, fail fast (caller should prompt user gesture).
        // In practice the app calls unlock() from a user gesture before playback.
        if (!this._ctx) {
          try {
            const uri = `data:audio/wav;base64,${base64Wav}`
            if (this._htmlAudio) {
              try {
                this._htmlAudio.pause()
              } catch {
                // ignore
              }
              this._htmlAudio = null
            }
            const a = new Audio(uri)
            this._htmlAudio = a
            let started = false
            const fireStart = () => {
              if (started) return
              started = true
              try {
                onStart?.(performance.now())
              } catch {
                // ignore
              }
            }
            a.onended = () => {
              if (this._htmlAudio === a) this._htmlAudio = null
              finish()
            }
            a.onerror = () => {
              if (this._htmlAudio === a) this._htmlAudio = null
              fail(new Error('HTMLAudio playback failed (autoplay policy?)'))
            }
            // Best-effort signal for the *actual* playback start.
            try {
              a.addEventListener('playing', fireStart, { once: true })
            } catch {
              // ignore
            }
            const p = a.play()
            if (p) {
              p.catch((e) => {
                if (this._htmlAudio === a) this._htmlAudio = null
                fail(e instanceof Error ? e : new Error(String(e)))
              })
            }
            // If the browser doesn't fire 'playing' (rare), still start visemes.
            window.setTimeout(fireStart, 0)
            return
          } catch (e) {
            fail(e instanceof Error ? e : new Error(String(e)))
            return
          }
        }
        if (this._ctx.state === 'suspended') {
          fail(new Error('AudioContext is suspended (autoplay policy?)'))
          return
        }

        let bytes: Uint8Array
        try {
          const binary = atob(base64Wav)
          bytes = new Uint8Array(binary.length)
          for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
        } catch (e) {
          console.error('Base64 decode error:', e)
          fail(e instanceof Error ? e : new Error(String(e)))
          return
        }

        try {
          const arrayBuffer = bytes.buffer as ArrayBuffer
          const buffer = await this._ctx.decodeAudioData(arrayBuffer)
          this.stop()
          this._source = this._ctx.createBufferSource()
          this._source.buffer = buffer
          this._source.connect(this._ctx.destination)
          this._source.onended = () => {
            this._source = null
            finish()
          }
          this._source.start(0)
          try {
            onStart?.(performance.now())
          } catch {
            // ignore
          }
        } catch (e) {
          console.error('Audio decode error:', e)
          fail(e instanceof Error ? e : new Error(String(e)))
        }
      })()
    })
  }

  async enqueue(base64Wav: string): Promise<{ startTimeMs: number; durationMs: number; ended: Promise<void> }> {
    await this.unlock()
    this._ensureCtx()
    if (!this._ctx) throw new Error('AudioContext not available')
    if (this._ctx.state === 'suspended') {
      try {
        await this._ctx.resume()
      } catch {
        // ignore
      }
    }
    if (this._ctx.state === 'suspended') throw new Error('AudioContext is suspended (autoplay policy?)')
    if (!base64Wav) throw new Error('No audio provided')

    let bytes: Uint8Array
    try {
      const binary = atob(base64Wav)
      bytes = new Uint8Array(binary.length)
      for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
    } catch (e) {
      throw e instanceof Error ? e : new Error(String(e))
    }

    const buffer = await this._ctx.decodeAudioData(bytes.buffer as ArrayBuffer)
    const now = this._ctx.currentTime
    const when = Math.max(now, this._nextStartTime ?? now)
    this._nextStartTime = when + buffer.duration

    const source = this._ctx.createBufferSource()
    source.buffer = buffer
    source.connect(this._ctx.destination)
    this._scheduled.push(source)

    let resolveEnded: (() => void) | null = null
    const ended = new Promise<void>((resolve) => (resolveEnded = resolve))
    source.onended = () => {
      this._scheduled = this._scheduled.filter((s) => s !== source)
      resolveEnded?.()
    }

    source.start(when)
    const startTimeMs = performance.now() + Math.max(0, when - now) * 1000
    return { startTimeMs, durationMs: buffer.duration * 1000, ended }
  }

  stop(): void {
    if (this._source) {
      try {
        this._source.stop()
      } catch {
        // ignore
      }
      this._source = null
    }
    if (this._htmlAudio) {
      try {
        this._htmlAudio.pause()
      } catch {
        // ignore
      }
      this._htmlAudio = null
    }
    if (this._scheduled.length) {
      for (const s of this._scheduled) {
        try {
          s.stop()
        } catch {
          // ignore
        }
      }
      this._scheduled = []
    }
    this._nextStartTime = null
  }
}
