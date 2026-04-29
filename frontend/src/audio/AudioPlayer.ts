export class AudioPlayer {
  _ctx: AudioContext | null = null
  _source: AudioBufferSourceNode | null = null

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

  async play(base64Wav: string, onEnd?: () => void): Promise<void> {
    return await new Promise<void>((resolve) => {
      const finish = () => {
        onEnd?.()
        resolve()
      }

      if (!base64Wav) {
        finish()
        return
      }

      void (async () => {
        await this.unlock()
        if (!this._ctx) {
          console.error('AudioContext not available')
          finish()
          return
        }
        if (this._ctx.state === 'suspended') {
          console.warn('AudioContext is suspended (autoplay policy?)')
          finish()
          return
        }

        let bytes: Uint8Array
        try {
          const binary = atob(base64Wav)
          bytes = new Uint8Array(binary.length)
          for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
        } catch (e) {
          console.error('Base64 decode error:', e)
          finish()
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
        } catch (e) {
          console.error('Audio decode error:', e)
          finish()
        }
      })()
    })
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
  }
}

