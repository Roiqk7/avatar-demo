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
  _queuedChunks = 0
  _pendingVisemeTimers: number[] = []

  mood: 'neutral' | 'sad' = 'neutral'

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

  _dvdEnabled = false
  _dvdTargetScale = 0.375
  _dvdScale = 1
  _dvdTx = 0
  _dvdTy = 0
  _dvdVx = 0.055 // px / ms (+10%)
  _dvdVy = 0.044 // px / ms (+10%)
  _dvdLastMs = 0

  _transformActive = false
  _transformStartMs = 0
  _transformDurMs = 0
  _transformFrom = { tx: 0, ty: 0, scale: 1 }
  _transformTo = { tx: 0, ty: 0, scale: 1 }

  _idleFloatEnabled = true
  _idleFloatAmpX = 4.5 // px
  _idleFloatAmpY = 3.0 // px
  _idleFloatPeriodMs = 8000 // slow + smooth

  _faceOverrideSrc: string | null = null
  _faceOverrideImg: HTMLImageElement | null = null
  _faceCrop: { sx: number; sy: number; sw: number; sh: number } | null = null
  _faceProcessed: HTMLCanvasElement | null = null

  _speechRotationActive = false
  _speechRotationStartMs = 0
  _speechRotationDurMs = 0
  _speechRotationTurns = 0

  _blackHoleActive = false
  _blackHoleStartMs = 0
  _blackHoleSpiralMs = 850
  _blackHoleHoldMs = 2000
  _blackHoleFadeInMs = 950
  _blackHoleRecenterToCanvas = true

  _lastWallHit: 'left' | 'right' | 'top' | 'bottom' | null = null
  _lastWallHitMs = 0

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

  setMood(mood: 'neutral' | 'sad') {
    this.mood = mood
  }

  setFaceOverride(src: string | null) {
    if (src === this._faceOverrideSrc) return
    this._faceOverrideSrc = src
    this._faceOverrideImg = null
    if (!src) return
    const img = new Image()
    img.onload = () => {
      if (this._faceOverrideSrc !== src) return
      this._faceOverrideImg = img
    }
    img.onerror = () => {
      if (this._faceOverrideSrc !== src) return
      console.warn('[avatar] failed to load face override', src)
      this._faceOverrideImg = null
    }
    img.src = src
  }

  _computeAlphaCrop(img: HTMLImageElement): { sx: number; sy: number; sw: number; sh: number } | null {
    const w = img.naturalWidth || img.width
    const h = img.naturalHeight || img.height
    if (!(w > 0 && h > 0)) return null

    // Draw into an offscreen canvas and find the bounding box of non-transparent pixels.
    const c = document.createElement('canvas')
    c.width = w
    c.height = h
    const cctx = c.getContext('2d', { willReadFrequently: true })
    if (!cctx) return null
    cctx.clearRect(0, 0, w, h)
    cctx.drawImage(img, 0, 0, w, h)
    const data = cctx.getImageData(0, 0, w, h).data

    let minX = w,
      minY = h,
      maxX = -1,
      maxY = -1
    const alphaThreshold = 8
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        const a = data[(y * w + x) * 4 + 3]!
        if (a > alphaThreshold) {
          if (x < minX) minX = x
          if (y < minY) minY = y
          if (x > maxX) maxX = x
          if (y > maxY) maxY = y
        }
      }
    }

    if (maxX < minX || maxY < minY) return null

    const pad = 4
    minX = Math.max(0, minX - pad)
    minY = Math.max(0, minY - pad)
    maxX = Math.min(w - 1, maxX + pad)
    maxY = Math.min(h - 1, maxY + pad)
    return { sx: minX, sy: minY, sw: maxX - minX + 1, sh: maxY - minY + 1 }
  }

  _tintToEmojiYellow(srcCanvas: HTMLCanvasElement): HTMLCanvasElement {
    const w = srcCanvas.width
    const h = srcCanvas.height
    const out = document.createElement('canvas')
    out.width = w
    out.height = h
    const octx = out.getContext('2d', { willReadFrequently: true })
    const sctx = srcCanvas.getContext('2d', { willReadFrequently: true })
    if (!octx || !sctx) return srcCanvas

    const img = sctx.getImageData(0, 0, w, h)
    const d = img.data
    const baseR = 0xff
    const baseG = 0xcc
    const baseB = 0x4d
    for (let i = 0; i < d.length; i += 4) {
      const a = d[i + 3]!
      if (a === 0) continue
      // Flat recolor (no luminance preservation) so it matches emoji eye-ring yellow.
      d[i] = baseR
      d[i + 1] = baseG
      d[i + 2] = baseB
    }
    octx.putImageData(img, 0, 0)
    return out
  }

  startSpeechRotation(opts: { turns: number; durationMs: number }) {
    const now = performance.now()
    const dur = Math.max(0, opts.durationMs)
    if (!(dur > 0) || !(opts.turns > 0)) {
      this._speechRotationActive = false
      return
    }
    this._speechRotationActive = true
    this._speechRotationStartMs = now
    this._speechRotationDurMs = dur
    this._speechRotationTurns = opts.turns
  }

  getDvdModeEnabled(): boolean {
    return this._dvdEnabled
  }

  getBlackHoleTotalMs(): number {
    return this._blackHoleSpiralMs + this._blackHoleHoldMs + this._blackHoleFadeInMs
  }

  triggerBlackHole(opts?: { recenterToCanvas?: boolean }) {
    const now = performance.now()
    this._blackHoleActive = true
    this._blackHoleStartMs = now
    this._blackHoleRecenterToCanvas = opts?.recenterToCanvas ?? true
    // Ensure other motions don't fight during the sequence.
    this._transformActive = false
  }

  setDvdMode(enabled: boolean) {
    if (enabled === this._dvdEnabled) return
    this._dvdEnabled = enabled
    this._dvdLastMs = performance.now()

    if (enabled) {
      // Smooth enter into DVD mode: shrink + recenter, then start bouncing.
      const now = performance.now()
      // Always animate from identity to avoid snapping.
      this._dvdTx = 0
      this._dvdTy = 0
      this._dvdScale = 1

      const to = this._computeCenteredTransform(this._dvdTargetScale)
      // Linear enter transition (2s).
      this._startTransform(now, 2000, { tx: to.tx, ty: to.ty, scale: this._dvdTargetScale })

      // Deterministic but non-axis-aligned direction.
      this._dvdVx = 0.055
      this._dvdVy = 0.044
    } else {
      // Exiting DVD mode is controlled via recenterDvd (called by UI on activity).
      this._transformActive = false
    }
  }

  recenterDvd(opts?: { animateMs?: number }) {
    const dur = Math.max(0, opts?.animateMs ?? 0)
    const now = performance.now()
    if (dur > 0) {
      this._startTransform(now, dur, { tx: 0, ty: 0, scale: 1 })
    }

    if (dur === 0) {
      this._dvdTx = 0
      this._dvdTy = 0
      this._dvdScale = 1
      this._transformActive = false
    }
  }

  _startTransform(now: number, durMs: number, to: { tx: number; ty: number; scale: number }) {
    this._transformActive = durMs > 0
    this._transformStartMs = now
    this._transformDurMs = Math.max(1, durMs)
    this._transformFrom = { tx: this._dvdTx, ty: this._dvdTy, scale: this._dvdScale }
    this._transformTo = to
  }

  _easeLinear(t: number): number {
    return t
  }

  _easeInOutSine(t: number): number {
    return 0.5 - 0.5 * Math.cos(Math.PI * Math.min(1, Math.max(0, t)))
  }

  _easeInQuad(t: number): number {
    const u = Math.min(1, Math.max(0, t))
    return u * u
  }

  _easeInExpo(t: number): number {
    const u = Math.min(1, Math.max(0, t))
    if (u === 0) return 0
    return Math.pow(2, 10 * (u - 1))
  }

  _idleFloatOffset(now: number): { x: number; y: number } {
    if (!this._idleFloatEnabled) return { x: 0, y: 0 }
    if (this._dvdEnabled) return { x: 0, y: 0 }
    if (this._blackHoleActive) return { x: 0, y: 0 }
    const t = (now - this.globalStartMs) / Math.max(1, this._idleFloatPeriodMs)
    const a = 2 * Math.PI * t
    const x = this._idleFloatAmpX * Math.sin(a)
    const y = this._idleFloatAmpY * Math.sin(2 * a)
    return { x, y }
  }

  _speechRotationAngle(now: number): number {
    if (!this._speechRotationActive) return 0
    const elapsed = now - this._speechRotationStartMs
    if (elapsed < 0) return 0
    if (elapsed >= this._speechRotationDurMs) {
      this._speechRotationActive = false
      return 0
    }
    const t = elapsed / Math.max(1, this._speechRotationDurMs)

    // Accelerating spin curve:
    // - first rotation takes ~25% of the time (e.g. 0.5s of 2s)
    // - remaining 5 rotations happen over the remaining 75% with exponential ease-in
    const firstFrac = 0.25
    const firstTurnsFrac = 1 / 6
    let turnsProgressFrac: number
    if (t <= firstFrac) {
      const u = t / Math.max(1e-6, firstFrac)
      turnsProgressFrac = firstTurnsFrac * this._easeInQuad(u)
    } else {
      const u = (t - firstFrac) / Math.max(1e-6, 1 - firstFrac)
      turnsProgressFrac = firstTurnsFrac + (1 - firstTurnsFrac) * this._easeInExpo(u)
    }

    return 2 * Math.PI * this._speechRotationTurns * turnsProgressFrac
  }

  _blackHoleState(now: number): {
    active: boolean
    alpha: number
    scale: number
    rot: number
    tx: number
    ty: number
    pivot: 'canvas' | 'avatar'
  } {
    if (!this._blackHoleActive) return { active: false, alpha: 1, scale: 1, rot: 0, tx: 0, ty: 0, pivot: 'canvas' }

    const spiralEnd = this._blackHoleSpiralMs
    const holdEnd = spiralEnd + this._blackHoleHoldMs
    const fadeEnd = holdEnd + this._blackHoleFadeInMs
    const t = now - this._blackHoleStartMs

    const shouldRecenter = this._blackHoleRecenterToCanvas
    const center = this._computeCenteredTransform(1)
    const toCenterTx = shouldRecenter ? center.tx - this._dvdTx : 0
    const toCenterTy = shouldRecenter ? center.ty - this._dvdTy : 0
    const pivot: 'canvas' | 'avatar' = shouldRecenter ? 'canvas' : 'avatar'

    if (t <= spiralEnd) {
      const u = this._easeInOutSine(t / spiralEnd)
      const scale = 1 - 0.92 * u
      // End at a "square" rotation so the farthest-away pose is aligned.
      const rot = 2 * Math.PI * 2.0 * u
      const alpha = 1 - 0.95 * u
      return { active: true, alpha, scale, rot, tx: toCenterTx * u, ty: toCenterTy * u, pivot }
    }

    if (t <= holdEnd) {
      return { active: true, alpha: 0, scale: 0.08, rot: 2 * Math.PI * 2.0, tx: toCenterTx, ty: toCenterTy, pivot }
    }

    if (t <= fadeEnd) {
      const u = this._easeInOutSine((t - holdEnd) / this._blackHoleFadeInMs)
      const alpha = u
      const scale = 0.08 + (1 - 0.08) * u
      const rot = 2 * Math.PI * 0.15 * (1 - u)
      const tx = toCenterTx * (1 - u)
      const ty = toCenterTy * (1 - u)
      return { active: true, alpha, scale, rot, tx, ty, pivot }
    }

    this._blackHoleActive = false
    return { active: false, alpha: 1, scale: 1, rot: 0, tx: 0, ty: 0, pivot: 'canvas' }
  }

  _computeCenteredTransform(scale: number): { tx: number; ty: number } {
    // Choose (tx,ty) so the face is centered in the canvas at the given scale.
    const cx = this.W / 2
    const cy = this.H / 2
    const faceCx = this._faceX + this._faceWidth / 2
    const faceCy = this._faceY + this._faceDH / 2
    return { tx: cx - scale * faceCx, ty: cy - scale * faceCy }
  }

  _avatarBoundsLocal(opts?: { shrink?: number }): { left: number; top: number; right: number; bottom: number } {
    // Bounding box for everything we might draw (face + worst-case eyes/mouth extents).
    // We use maxW/maxH for eyes/mouth since actual sprite aspect ratios vary.
    const faceLeft = this._faceX
    const faceTop = this._faceY
    const faceRight = this._faceX + this._faceWidth
    const faceBottom = this._faceY + this._faceDH

    const eyeLeft = this._eyeCX - this._eyeMaxW / 2
    const eyeTop = this._eyeCY - this._eyeMaxH / 2
    const eyeRight = this._eyeCX + this._eyeMaxW / 2
    const eyeBottom = this._eyeCY + this._eyeMaxH / 2

    const mouthLeft = this._mouthCX - this._mouthMaxW / 2
    const mouthTop = this._mouthCY - this._mouthMaxH / 2
    const mouthRight = this._mouthCX + this._mouthMaxW / 2
    const mouthBottom = this._mouthCY + this._mouthMaxH / 2

    return {
      left: this._shrinkBounds(Math.min(faceLeft, eyeLeft, mouthLeft), Math.max(faceRight, eyeRight, mouthRight), opts?.shrink).a,
      right: this._shrinkBounds(Math.min(faceLeft, eyeLeft, mouthLeft), Math.max(faceRight, eyeRight, mouthRight), opts?.shrink).b,
      top: this._shrinkBounds(Math.min(faceTop, eyeTop, mouthTop), Math.max(faceBottom, eyeBottom, mouthBottom), opts?.shrink).a,
      bottom: this._shrinkBounds(Math.min(faceTop, eyeTop, mouthTop), Math.max(faceBottom, eyeBottom, mouthBottom), opts?.shrink).b,
    }
  }

  _shrinkBounds(a: number, b: number, shrink?: number): { a: number; b: number } {
    const s = shrink ?? 1
    if (!(s > 0 && s <= 1)) return { a, b }
    const mid = (a + b) / 2
    const half = ((b - a) / 2) * s
    return { a: mid - half, b: mid + half }
  }

  _stepDvd(now: number) {
    const dt = Math.max(0, Math.min(33, now - this._dvdLastMs))
    this._dvdLastMs = now

    // If we're in a transform animation (enter/exit), override DVD motion.
    if (this._transformActive) {
      const t = Math.min(1, (now - this._transformStartMs) / this._transformDurMs)
      const ease = this._easeLinear(t)
      this._dvdTx = this._transformFrom.tx + (this._transformTo.tx - this._transformFrom.tx) * ease
      this._dvdTy = this._transformFrom.ty + (this._transformTo.ty - this._transformFrom.ty) * ease
      this._dvdScale = this._transformFrom.scale + (this._transformTo.scale - this._transformFrom.scale) * ease
      if (t >= 1) this._transformActive = false
      return
    }

    if (!this._dvdEnabled || this.playing) return

    this._dvdTx += this._dvdVx * dt
    this._dvdTy += this._dvdVy * dt

    // Bounds based on the full drawn avatar (face + eyes/mouth worst-case extents),
    // so the visible emoji can truly hit canvas edges without clipping.
    const b = this._avatarBoundsLocal()
    const s = this._dvdScale
    const left = s * b.left + this._dvdTx
    const top = s * b.top + this._dvdTy
    const right = s * b.right + this._dvdTx
    const bottom = s * b.bottom + this._dvdTy

    // Bounce off canvas edges.
    if (left < 0) {
      this._dvdTx += -left
      this._dvdVx = Math.abs(this._dvdVx)
      this._lastWallHit = 'left'
      this._lastWallHitMs = now
    } else if (right > this.W) {
      this._dvdTx -= right - this.W
      this._dvdVx = -Math.abs(this._dvdVx)
      this._lastWallHit = 'right'
      this._lastWallHitMs = now
    }

    if (top < 0) {
      this._dvdTy += -top
      this._dvdVy = Math.abs(this._dvdVy)
      this._lastWallHit = 'top'
      this._lastWallHitMs = now
    } else if (bottom > this.H) {
      this._dvdTy -= bottom - this.H
      this._dvdVy = -Math.abs(this._dvdVy)
      this._lastWallHit = 'bottom'
      this._lastWallHitMs = now
    }
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

    // For SignoFace, auto-crop transparent padding and pre-tint to emoji-yellow once.
    this._faceCrop = null
    this._faceProcessed = null
    if (p.id === 'signoface' && this.assets.face) {
      const crop = this._computeAlphaCrop(this.assets.face)
      if (crop) {
        const c = document.createElement('canvas')
        c.width = crop.sw
        c.height = crop.sh
        const cctx = c.getContext('2d', { willReadFrequently: true })
        if (cctx) {
          cctx.drawImage(this.assets.face, crop.sx, crop.sy, crop.sw, crop.sh, 0, 0, crop.sw, crop.sh)
          this._faceProcessed = this._tintToEmojiYellow(c)
        }
      }
    } else if (this.assets.face) {
      // Generic crop for other personalities if needed later (currently unused).
      this._faceCrop = null
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

    // Keep transforms consistent after changing layout/assets.
    // Only recompute centering if we're currently in a transformed mode.
    if (this._dvdEnabled || this._transformActive) {
      const centered = this._computeCenteredTransform(this._dvdScale)
      this._dvdTx = centered.tx
      this._dvdTy = centered.ty
    } else {
      this._dvdTx = 0
      this._dvdTy = 0
      this._dvdScale = 1
    }
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
    // Cancel any pending viseme timeline switches (queued chunks).
    if (this._pendingVisemeTimers.length) {
      for (const id of this._pendingVisemeTimers) {
        try {
          window.clearTimeout(id)
        } catch {
          // ignore
        }
      }
      this._pendingVisemeTimers = []
    }
    const now = performance.now() - this.globalStartMs
    this.mouthCtrl?.notifyIdle(now)
    this.emoteCtrl?.notifyIdle(now)
  }

  interrupt(): void {
    // Used for barge-in: stop audio immediately and reset mouth/eye state.
    this.audioPlayer.stop()
    if (this.playing) this.stopPlayback()
    this._queuedChunks = 0
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

    this._stepDvd(now)

    const idle = this._idleFloatOffset(now)
    const speechRot = this._speechRotationAngle(now)
    const bh = this._blackHoleState(now)

    const useTransform =
      (this._dvdEnabled && !this.playing) ||
      this._transformActive ||
      (idle.x !== 0 || idle.y !== 0) ||
      speechRot !== 0 ||
      bh.active

    if (useTransform) {
      ctx.save()

      // Start with the existing (dvd/transform) translation+scale, then layer in small idle offsets.
      const baseScale = this._dvdScale
      const baseTx = this._dvdTx + idle.x
      const baseTy = this._dvdTy + idle.y
      ctx.setTransform(baseScale, 0, 0, baseScale, baseTx, baseTy)

      // Black-hole sequence: additional translate/rotate/scale around canvas center.
      if (bh.active) {
        if (bh.pivot === 'avatar') {
          const faceCx = this._faceX + this._faceWidth / 2
          const faceCy = this._faceY + this._faceDH / 2
          ctx.translate(faceCx, faceCy)
          ctx.rotate(bh.rot)
          ctx.scale(bh.scale, bh.scale)
          ctx.translate(-faceCx, -faceCy)
          ctx.translate(bh.tx, bh.ty)
        } else {
          ctx.translate(this.W / 2, this.H / 2)
          ctx.rotate(bh.rot)
          ctx.scale(bh.scale, bh.scale)
          ctx.translate(-this.W / 2, -this.H / 2)
          ctx.translate(bh.tx, bh.ty)
        }
        if (bh.alpha < 1) ctx.globalAlpha = bh.alpha
      }

      // Speech rotation: full-avatar rotation around canvas center.
      if (speechRot !== 0) {
        const faceCx = this._faceX + this._faceWidth / 2
        const faceCy = this._faceY + this._faceDH / 2
        ctx.translate(faceCx, faceCy)
        ctx.rotate(speechRot)
        ctx.translate(-faceCx, -faceCy)
      }
    }

    const face = this._faceOverrideImg ?? this.assets.face
    const isOverride = Boolean(this._faceOverrideImg)
    const signoProcessed = !isOverride && this.personality?.id === 'signoface' ? this._faceProcessed : null

    if (signoProcessed) {
      // Preserve aspect ratio (contain) so the logo isn't stretched.
      const sw = signoProcessed.width
      const sh = signoProcessed.height
      const r = Math.min(this._faceWidth / sw, this._faceDH / sh)
      const dw = sw * r
      const dh = sh * r
      const dx = this._faceX + (this._faceWidth - dw) / 2
      const dy = this._faceY + (this._faceDH - dh) / 2
      ctx.drawImage(signoProcessed, dx, dy, dw, dh)
    } else if (this._faceCrop && !isOverride) {
      // Preserve aspect ratio for cropped art.
      const { sx, sy, sw, sh } = this._faceCrop
      const r = Math.min(this._faceWidth / sw, this._faceDH / sh)
      const dw = sw * r
      const dh = sh * r
      const dx = this._faceX + (this._faceWidth - dw) / 2
      const dy = this._faceY + (this._faceDH - dh) / 2
      ctx.drawImage(face, sx, sy, sw, sh, dx, dy, dw, dh)
    } else {
      ctx.drawImage(face, this._faceX, this._faceY, this._faceWidth, this._faceDH)
    }

    let activeViseme = 0
    if (this.playing) {
      const audioElapsed = Math.max(0, now - this.audioStartMs)
      activeViseme = this._getActiveViseme(audioElapsed)
    } else {
      this.mouthCtrl?.notifyIdle(eyeElapsed)
      this.emoteCtrl?.notifyIdle(eyeElapsed)
    }

    const availableMouthNames = new Set(Object.keys(this.assets.idleMouths || {}))
    if (this.mood !== 'sad') {
      this.emoteCtrl?.update(eyeElapsed, this.eyeCtrl!, this.mouthCtrl!, availableMouthNames)
    }

    if (Object.keys(this.assets.eyes).length) {
      if (this.mood === 'sad') {
        // Force a semi-closed look. Prefer the half-blink sprite if present.
        const sadEye = this.assets.eyes[3] || this.assets.eyes[4] || this.assets.eyes[12]
        if (sadEye) this._drawImageCentered(sadEye, this._eyeCX, this._eyeCY, this._eyeMaxW, this._eyeMaxH)
      } else if (this.eyeCtrl) {
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
    }

    if (this.mood === 'sad') {
      const sad = this.assets.idleMouths['sad2'] || this.assets.idleMouths['sad'] || null
      if (sad) this._drawImageCentered(sad, this._mouthCX, this._mouthCY, this._mouthMaxW, this._mouthMaxH)
      else if (this.playing) {
        const img = this.assets.visemes[activeViseme]
        if (img) this._drawImageCentered(img, this._mouthCX, this._mouthCY, this._mouthMaxW, this._mouthMaxH)
      } else {
        const idle = this.mouthCtrl?.getIdleMouth(eyeElapsed, availableMouthNames) ?? { prev: null, cur: null, t: 1 }
        this._drawIdleMouth(idle.prev, idle.cur, idle.t)
      }
    } else if (this.playing) {
      const img = this.assets.visemes[activeViseme]
      if (img) this._drawImageCentered(img, this._mouthCX, this._mouthCY, this._mouthMaxW, this._mouthMaxH)
    } else {
      const idle = this.mouthCtrl?.getIdleMouth(eyeElapsed, availableMouthNames) ?? { prev: null, cur: null, t: 1 }
      this._drawIdleMouth(idle.prev, idle.cur, idle.t)
    }

    if (useTransform) {
      ctx.restore()
    }

    // Flash the wall edge briefly on collision.
    const wallAge = now - this._lastWallHitMs
    if (this._lastWallHit && wallAge >= 0 && wallAge <= 220) {
      const t = 1 - wallAge / 220
      ctx.save()
      ctx.globalAlpha = 0.55 * t
      ctx.strokeStyle = '#ffffff'
      ctx.lineWidth = 6
      ctx.beginPath()
      if (this._lastWallHit === 'left') {
        ctx.moveTo(0, 0)
        ctx.lineTo(0, this.H)
      } else if (this._lastWallHit === 'right') {
        ctx.moveTo(this.W, 0)
        ctx.lineTo(this.W, this.H)
      } else if (this._lastWallHit === 'top') {
        ctx.moveTo(0, 0)
        ctx.lineTo(this.W, 0)
      } else if (this._lastWallHit === 'bottom') {
        ctx.moveTo(0, this.H)
        ctx.lineTo(this.W, this.H)
      }
      ctx.stroke()
      ctx.restore()
    }

    const visemeLabel = this.playing
      ? `${activeViseme}(${this.personality?.viseme_labels[activeViseme] || '?'})`
      : '-'
    const mouthSprite = this.playing
      ? this.personality?.viseme_labels[activeViseme] || '?'
      : this.mouthCtrl?._current || '-'
    const eyeLabel = this.eyeCtrl ? `${this.eyeCtrl._current}(${this.eyeCtrl.stateLabel})` : '-'
    const state = this.playing ? 'Speaking' : 'Listening'
    this.onHud?.(`${state} | Viseme: ${visemeLabel} | Mouth: ${mouthSprite} | Eye: ${eyeLabel}`)
  }

  async playTts(base64Wav: string, visemes: VisemeOut[], onDone?: () => void, onError?: (err: Error) => void): Promise<void> {
    let didStart = false
    await this.audioPlayer.play(
      base64Wav,
      () => {
        this.stopPlayback()
        onDone?.()
      },
      (err) => {
        this.stopPlayback()
        onError?.(err)
      },
      (startTimeMs) => {
        if (didStart) return
        didStart = true
        this.startPlayback(visemes, startTimeMs)
      },
    )
  }

  async queueTtsChunk(base64Wav: string, visemes: VisemeOut[]): Promise<boolean> {
    this._queuedChunks += 1
    let scheduled = false
    try {
      const { startTimeMs, ended } = await this.audioPlayer.enqueue(base64Wav)
      scheduled = true
      // Important: for chunk 2+, startTimeMs is often in the future.
      // Do NOT overwrite the current viseme timeline until this chunk actually begins.
      const delayMs = Math.max(0, startTimeMs - performance.now())
      const timerId = window.setTimeout(() => {
        this._pendingVisemeTimers = this._pendingVisemeTimers.filter((x) => x !== timerId)
        this.startPlayback(visemes, startTimeMs)
      }, delayMs)
      this._pendingVisemeTimers.push(timerId)
      void ended.then(() => {
        this._queuedChunks = Math.max(0, this._queuedChunks - 1)
        if (this._queuedChunks === 0) this.stopPlayback()
      })
      return true
    } catch (e) {
      return false
    } finally {
      if (!scheduled) {
        this._queuedChunks = Math.max(0, this._queuedChunks - 1)
        if (this._queuedChunks === 0) this.stopPlayback()
      }
    }
  }
}

