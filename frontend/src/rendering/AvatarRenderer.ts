import type { Personality, VisemeOut } from '../types'
import { AudioPlayer } from '../audio/AudioPlayer'
import { EyeController } from './EyeController'
import { MouthController } from './MouthController'
import { EmoteController } from './EmoteController'
import { loadPersonalityAssets, type PersonalityAssets } from './assets'

export class AvatarRenderer {
  canvas: HTMLCanvasElement
  ctx: CanvasRenderingContext2D
  W: number
  H: number

  personality: Personality | null = null
  assets: PersonalityAssets | null = null
  eyeCtrl: EyeController | null = null
  mouthCtrl: MouthController | null = null
  emoteCtrl: EmoteController | null = null

  playing = false
  visemes: VisemeOut[] = []
  audioStartMs = 0

  globalStartMs = performance.now()
  _running = false
  _raf: number | null = null

  _faceWidth = 430
  _faceX = 0
  _faceY = 50
  _faceDH = 430
  _mouthMaxW = 0
  _mouthMaxH = 0
  _eyeMaxW = 0
  _eyeMaxH = 0
  _mouthCX = 0
  _mouthCY = 0
  _eyeCX = 0
  _eyeCY = 0

  audioPlayer = new AudioPlayer()

  onHud?: (text: string) => void
  onError?: (text: string) => void
  _applyToken = 0

  constructor(canvas: HTMLCanvasElement) {
    this.canvas = canvas
    const ctx = canvas.getContext('2d')
    if (!ctx) throw new Error('2D canvas context not available')
    this.ctx = ctx
    this.W = canvas.width
    this.H = canvas.height
    this._render = this._render.bind(this)
  }

  async applyPersonality(p: Personality): Promise<void> {
    const token = ++this._applyToken
    this.personality = p
    const loaded = await loadPersonalityAssets(p)
    if (token !== this._applyToken) return
    this.assets = loaded
    if (!this.assets.face) {
      const msg = `Face image failed to load: ${p.assets.face_path}`
      this.onError?.(msg)
    }

    this.eyeCtrl = new EyeController(p.eye_config)
    this.mouthCtrl = new MouthController(p.idle_mouth_pools, p.mouth_timing, p.mouth_idle_enabled)
    this.emoteCtrl = new EmoteController(p.emotes, p.emote_timing)

    const fw = this._faceWidth
    const layout = p.face_layout
    this._mouthMaxW = fw * layout.mouth_width_ratio
    this._mouthMaxH = fw * layout.mouth_height_ratio
    this._eyeMaxW = fw * layout.eye_width_ratio
    this._eyeMaxH = fw * layout.eye_height_ratio

    let faceH = fw
    if (this.assets.face) {
      faceH = (this.assets.face.height / this.assets.face.width) * fw
    }

    this._faceX = (this.W - fw) / 2
    this._faceY = 50
    this._faceDH = faceH
    this._mouthCX = this._faceX + fw / 2
    this._mouthCY = this._faceY + faceH * layout.mouth_y_ratio
    this._eyeCX = this._faceX + fw / 2
    this._eyeCY = this._faceY + faceH * layout.eye_y_ratio
  }

  startPlayback(visemes: VisemeOut[], audioStartMs: number): void {
    this.visemes = visemes
    this.audioStartMs = audioStartMs
    this.playing = true
    this.mouthCtrl?.notifySpeaking()
    this.emoteCtrl?.notifySpeaking()
  }

  stopPlayback(): void {
    this.playing = false
    const now = performance.now() - this.globalStartMs
    this.mouthCtrl?.notifyIdle(now)
    this.emoteCtrl?.notifyIdle(now)
  }

  start(): void {
    if (this._running) return
    this._running = true
    this._raf = requestAnimationFrame(this._render)
  }

  stop(): void {
    this._running = false
    if (this._raf) cancelAnimationFrame(this._raf)
    this._raf = null
  }

  _getActiveViseme(elapsedMs: number): number {
    let active = 0
    for (const v of this.visemes) {
      if (v.offset_ms <= elapsedMs) active = v.id
      else break
    }
    return active
  }

  _drawImageCentered(
    img: HTMLImageElement | undefined | null,
    cx: number,
    cy: number,
    maxW: number,
    maxH: number,
    alpha = 1,
  ) {
    if (!img) return
    const r = Math.min(maxW / img.width, maxH / img.height)
    const w = img.width * r
    const h = img.height * r
    const x = cx - w / 2
    const y = cy - h / 2

    if (alpha < 1) this.ctx.globalAlpha = alpha
    this.ctx.drawImage(img, x, y, w, h)
    if (alpha < 1) this.ctx.globalAlpha = 1
  }

  _resolveMouthImg(name: string | null): HTMLImageElement | null {
    if (!this.assets) return null
    if (name === null) return this.assets.visemes[0] || null
    return this.assets.idleMouths[name] || null
  }

  _drawIdleMouth(prevName: string | null, curName: string | null, t: number) {
    const prevImg = this._resolveMouthImg(prevName)
    const curImg = this._resolveMouthImg(curName)
    const cx = this._mouthCX,
      cy = this._mouthCY
    const mw = this._mouthMaxW,
      mh = this._mouthMaxH

    if (t >= 1 || prevName === curName) {
      if (curImg) this._drawImageCentered(curImg, cx, cy, mw, mh)
    } else if (t >= 0.5) {
      if (curImg) this._drawImageCentered(curImg, cx, cy, mw, mh)
      if (prevImg && prevImg !== curImg) this._drawImageCentered(prevImg, cx, cy, mw, mh, (1 - t) * 2)
    } else {
      if (prevImg) this._drawImageCentered(prevImg, cx, cy, mw, mh)
      if (curImg && curImg !== prevImg) this._drawImageCentered(curImg, cx, cy, mw, mh, t * 2)
    }
  }

  _render() {
    if (!this._running) return
    this._raf = requestAnimationFrame(this._render)

    const ctx = this.ctx
    const now = performance.now()
    const eyeElapsed = now - this.globalStartMs

    ctx.clearRect(0, 0, this.W, this.H)

    if (!this.assets || !this.assets.face) {
      ctx.fillStyle = '#666'
      ctx.font = '16px "Space Mono"'
      ctx.textAlign = 'center'
      ctx.fillText('Loading assets...', this.W / 2, this.H / 2)
      return
    }

    ctx.drawImage(this.assets.face, this._faceX, this._faceY, this._faceWidth, this._faceDH)

    let activeViseme = 0
    if (this.playing) {
      const audioElapsed = now - this.audioStartMs
      activeViseme = this._getActiveViseme(audioElapsed)
    } else {
      this.mouthCtrl?.notifyIdle(eyeElapsed)
      this.emoteCtrl?.notifyIdle(eyeElapsed)
    }

    const availableMouthNames = new Set(Object.keys(this.assets.idleMouths || {}))
    this.emoteCtrl?.update(eyeElapsed, this.eyeCtrl!, this.mouthCtrl!, availableMouthNames)

    if (this.eyeCtrl && Object.keys(this.assets.eyes).length) {
      const blend = this.eyeCtrl.getBlend(eyeElapsed)
      const fromImg = this.assets.eyes[blend.fromIdx]
      const toImg = this.assets.eyes[blend.toIdx]

      if (blend.t >= 1 || blend.fromIdx === blend.toIdx) {
        if (toImg) this._drawImageCentered(toImg, this._eyeCX, this._eyeCY, this._eyeMaxW, this._eyeMaxH)
      } else if (blend.t >= 0.5) {
        if (toImg) this._drawImageCentered(toImg, this._eyeCX, this._eyeCY, this._eyeMaxW, this._eyeMaxH)
        if (fromImg && fromImg !== toImg) this._drawImageCentered(fromImg, this._eyeCX, this._eyeCY, this._eyeMaxW, this._eyeMaxH, (1 - blend.t) * 2)
      } else {
        if (fromImg) this._drawImageCentered(fromImg, this._eyeCX, this._eyeCY, this._eyeMaxW, this._eyeMaxH)
        if (toImg && toImg !== fromImg) this._drawImageCentered(toImg, this._eyeCX, this._eyeCY, this._eyeMaxW, this._eyeMaxH, blend.t * 2)
      }
    }

    if (this.playing) {
      const img = this.assets.visemes[activeViseme]
      if (img) this._drawImageCentered(img, this._mouthCX, this._mouthCY, this._mouthMaxW, this._mouthMaxH)
    } else {
      const idle = this.mouthCtrl?.getIdleMouth(eyeElapsed, availableMouthNames) ?? { prev: null, cur: null, t: 1 }
      this._drawIdleMouth(idle.prev, idle.cur, idle.t)
    }

    const mouthLabel = this.playing ? this.personality?.viseme_labels[activeViseme] || '?' : 'idle'
    const eyeLabel = this.eyeCtrl ? `${this.eyeCtrl._current}(${this.eyeCtrl.stateLabel})` : '-'
    const state = this.playing ? 'Speaking' : 'Listening'
    this.onHud?.(`${state} | Mouth: ${mouthLabel} | Eye: ${eyeLabel}`)
  }

  async playTts(base64Wav: string, visemes: VisemeOut[], onDone?: () => void): Promise<void> {
    this.startPlayback(visemes, performance.now())
    await this.audioPlayer.play(base64Wav, () => {
      this.stopPlayback()
      onDone?.()
    })
  }
}

