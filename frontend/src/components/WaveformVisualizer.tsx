import * as React from 'react'

type Props = {
  samplesRef: React.RefObject<Float32Array>
  isActive?: boolean
}

const A  = (alpha: number) => `rgba(59, 79, 228, ${alpha})`
const A2 = (alpha: number) => `rgba(90, 110, 247, ${alpha})`

function rmsSlice(s: Float32Array, i: number, N: number): number {
  const lo = Math.floor((i / N) * s.length)
  const hi = Math.floor(((i + 1) / N) * s.length)
  let sum = 0
  for (let j = lo; j < hi; j++) sum += (s[j] ?? 0) ** 2
  return Math.sqrt(sum / Math.max(1, hi - lo))
}

// Glow Accent — 28 bars, rms-proportional glow, asymmetric container corners
function drawBars(ctx: CanvasRenderingContext2D, w: number, h: number, s: Float32Array) {
  const N = 28, cy = h / 2, slotW = w / N
  const barW = slotW * 0.50
  for (let i = 0; i < N; i++) {
    const rmsVal = rmsSlice(s, i, N)
    const barH = Math.min(cy * 0.92, Math.max(2, rmsVal * cy * 4.5))
    const x = i * slotW + (slotW - barW) / 2
    const r = Math.min(barW / 2, barH / 2, 5)
    ctx.shadowColor = A(0.45)
    ctx.shadowBlur = Math.min(14, rmsVal * 90)
    ctx.fillStyle = A2(0.80)
    ctx.beginPath()
    ctx.roundRect(x, cy - barH / 2, barW, barH, r)
    ctx.fill()
  }
  ctx.shadowBlur = 0
}

export function WaveformVisualizer({ samplesRef, isActive }: Props) {
  const canvasRef = React.useRef<HTMLCanvasElement>(null)
  const rafRef = React.useRef<number | null>(null)
  const isActiveRef = React.useRef(isActive ?? true)

  React.useEffect(() => {
    isActiveRef.current = isActive ?? true
  }, [isActive])

  React.useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const sync = () => {
      const dpr = window.devicePixelRatio || 1
      const w = canvas.offsetWidth
      const h = canvas.offsetHeight
      if (canvas.width !== w * dpr) canvas.width = w * dpr
      if (canvas.height !== h * dpr) canvas.height = h * dpr
    }
    sync()
    const ro = new ResizeObserver(sync)
    ro.observe(canvas)
    return () => ro.disconnect()
  }, [])

  React.useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const draw = () => {
      rafRef.current = requestAnimationFrame(draw)

      const dpr = window.devicePixelRatio || 1
      const w = canvas.offsetWidth
      const h = canvas.offsetHeight
      if (canvas.width !== w * dpr) canvas.width = w * dpr
      if (canvas.height !== h * dpr) canvas.height = h * dpr
      if (w === 0 || h === 0) return

      const ctx = canvas.getContext('2d')
      if (!ctx) return

      ctx.save()
      ctx.scale(dpr, dpr)
      ctx.clearRect(0, 0, w, h)

      if (isActiveRef.current) {
        drawBars(ctx, w, h, samplesRef.current ?? new Float32Array(1024))
      }

      ctx.restore()
    }

    rafRef.current = requestAnimationFrame(draw)
    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current)
    }
  }, [samplesRef])

  return <canvas ref={canvasRef} className="waveform-canvas" />
}
