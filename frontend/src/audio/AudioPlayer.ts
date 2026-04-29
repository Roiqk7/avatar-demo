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
    if (!base64Wav) {
      onEnd?.()
      return
    }
    await this.unlock()
    if (!this._ctx) {
      console.error('AudioContext not available')
      onEnd?.()
      return
    }
    if (this._ctx.state === 'suspended') {
      console.warn('AudioContext is suspended (autoplay policy?)')
      onEnd?.()
      return
    }

    let bytes: Uint8Array
    try {
      const binary = atob(base64Wav)
      bytes = new Uint8Array(binary.length)
      for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
    } catch (e) {
      console.error('Base64 decode error:', e)
      onEnd?.()
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
        onEnd?.()
      }
      this._source.start(0)
    } catch (e) {
      console.error('Audio decode error:', e)
      onEnd?.()
    }
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

