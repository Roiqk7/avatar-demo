import * as React from 'react'
import type { Personality } from '../types'
import { AvatarRenderer } from '../rendering/AvatarRenderer'

export function AvatarCanvas(props: {
  personality: Personality | null
  onRenderer?: (r: AvatarRenderer | null) => void
  onHud?: (text: string) => void
}) {
  const { personality, onRenderer, onHud } = props
  const canvasRef = React.useRef<HTMLCanvasElement | null>(null)
  const rendererRef = React.useRef<AvatarRenderer | null>(null)
  const latestPersonalityRef = React.useRef<Personality | null>(null)
  const onHudRef = React.useRef(onHud)
  const onRendererRef = React.useRef(onRenderer)

  React.useEffect(() => {
    latestPersonalityRef.current = personality
  }, [personality])

  // Sync callback refs without recreating the renderer
  React.useEffect(() => {
    onHudRef.current = onHud
    if (rendererRef.current) rendererRef.current.onHud = onHud
  }, [onHud])

  React.useEffect(() => {
    onRendererRef.current = onRenderer
  }, [onRenderer])

  // Create renderer once; empty deps so inline callbacks never trigger teardown
  React.useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const r = new AvatarRenderer(canvas)
    rendererRef.current = r
    r.onHud = onHudRef.current
    r.start()
    onRendererRef.current?.(r)
    const p = latestPersonalityRef.current
    if (p) void r.applyPersonality(p)
    return () => {
      onRendererRef.current?.(null)
      r.stop()
      rendererRef.current = null
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  React.useEffect(() => {
    const r = rendererRef.current
    if (!r || !personality) return
    void r.applyPersonality(personality)
  }, [personality])

  return <canvas id="avatar-canvas" ref={canvasRef} width={600} height={600} />
}

