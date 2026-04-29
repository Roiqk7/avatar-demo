export class AudioPlayer {
  _ctx: AudioContext | null = null
  _source: AudioBufferSourceNode | null = null

  _ensureCtx() {
    if (!this._ctx) this._ctx = new (window.AudioContext || (window as any).webkitAudioContext)()
    if (this._ctx.state === 'suspended') void this._ctx.resume()
  }

  async play(base64Wav: string, onEnd?: () => void): Promise<void> {
    if (!base64Wav) {
      onEnd?.()
      return
    }
    this._ensureCtx()

    const binary = atob(base64Wav)
    const bytes = new Uint8Array(binary.length)
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)

    try {
      const buffer = await this._ctx!.decodeAudioData(bytes.buffer)
      this.stop()
      this._source = this._ctx!.createBufferSource()
      this._source.buffer = buffer
      this._source.connect(this._ctx!.destination)
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

