import type { Personality } from '../types'

export type PersonalityAssets = {
  face: HTMLImageElement | null
  visemes: Record<number, HTMLImageElement>
  eyes: Record<number, HTMLImageElement>
  idleMouths: Record<string, HTMLImageElement>
}

function loadImage(src: string): Promise<HTMLImageElement | null> {
  return new Promise((resolve) => {
    const img = new Image()
    img.onload = () => resolve(img)
    img.onerror = () => {
      console.warn('[assets] failed to load', src)
      resolve(null)
    }
    img.src = src
  })
}

async function loadEyeByIndex(eyesDir: string, idx: number): Promise<HTMLImageElement | null> {
  const NAMES = [
    'open-neutral',
    'open-pupils-left',
    'open-large-pupils',
    'blink-half-top',
    'blink-closed',
    'sleepy-asymmetric',
    'neutral',
    'angry',
    'looking-right',
    'squinting',
    'open-looking-up',
    'side-glance',
    'droopy',
    'crossed',
    'small-pupils',
  ]
  if (idx >= NAMES.length) return null
  return loadImage(`${eyesDir}/eye-${String(idx).padStart(2, '0')}-${NAMES[idx]}.png`)
}

export async function loadPersonalityAssets(p: Personality): Promise<PersonalityAssets> {
  const assets: PersonalityAssets = { face: null, visemes: {}, eyes: {}, idleMouths: {} }

  assets.face = await loadImage(p.assets.face_path)

  for (let i = 0; i < p.viseme_labels.length; i++) {
    const label = p.viseme_labels[i]!
    const img = await loadImage(`${p.assets.visemes_dir}/viseme-${String(i).padStart(2, '0')}-${label}.png`)
    if (img) assets.visemes[i] = img
  }

  for (let i = 0; i <= 14; i++) {
    const img = await loadEyeByIndex(p.assets.eyes_dir, i)
    if (img) assets.eyes[i] = img
  }

  for (const name of p.idle_mouth_names) {
    const img = await loadImage(`${p.assets.visemes_dir}/viseme-${name}.png`)
    if (img) assets.idleMouths[name] = img
  }

  // Optional "special" mouths that may be intentionally excluded from idle pools
  // (e.g. sad/cry) but still exist on disk for safety/UX moments.
  for (const name of ['sad2', 'sad', 'cry2', 'cry']) {
    if (assets.idleMouths[name]) continue
    const img = await loadImage(`${p.assets.visemes_dir}/viseme-${name}.png`)
    if (img) assets.idleMouths[name] = img
  }

  return assets
}

