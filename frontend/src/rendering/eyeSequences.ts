export type EyeSeqStep = [idx: number, transMs: number, holdMs: number]

export const SEQ_BLINK: EyeSeqStep[] = [
  [3, 90, 42],
  [4, 66, 66],
  [3, 66, 42],
  [0, 114, 0],
]
export const SEQ_SLOW_BLINK: EyeSeqStep[] = [
  [3, 138, 72],
  [4, 108, 108],
  [12, 96, 624],
  [3, 102, 60],
  [0, 168, 0],
]
export const SEQ_DOUBLE_BLINK: EyeSeqStep[] = [
  [3, 78, 34],
  [4, 60, 54],
  [3, 60, 34],
  [0, 72, 228],
  [3, 78, 34],
  [4, 60, 54],
  [3, 60, 34],
  [0, 120, 0],
]
export const SEQ_SPIN: EyeSeqStep[] = [
  [8, 138, 90],
  [10, 126, 78],
  [1, 126, 78],
  [11, 126, 78],
  [0, 186, 0],
]
export const SEQ_FRANTIC: EyeSeqStep[] = [
  [2, 90, 66],
  [14, 90, 66],
  [2, 90, 66],
  [14, 90, 66],
  [0, 192, 0],
]
export const SEQ_CROSSEYED: EyeSeqStep[] = [
  [13, 222, 432],
  [4, 72, 78],
  [13, 150, 372],
  [0, 252, 0],
]
export const SEQ_SHOCK_SQUINT: EyeSeqStep[] = [
  [2, 150, 468],
  [9, 270, 720],
  [0, 234, 0],
]
export const SEQ_CONFUSED: EyeSeqStep[] = [
  [10, 198, 240],
  [1, 174, 240],
  [5, 222, 504],
  [0, 222, 0],
]

export const BLINK_POOL: Array<{ seq: EyeSeqStep[]; weight: number }> = [
  { seq: SEQ_BLINK, weight: 0.65 },
  { seq: SEQ_SLOW_BLINK, weight: 0.2 },
  { seq: SEQ_DOUBLE_BLINK, weight: 0.15 },
]

export const GOOFY_POOL: EyeSeqStep[][] = [
  SEQ_SPIN,
  SEQ_FRANTIC,
  SEQ_CROSSEYED,
  SEQ_SHOCK_SQUINT,
  SEQ_CONFUSED,
]

