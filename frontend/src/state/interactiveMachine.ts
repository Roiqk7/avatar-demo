/**
 * Pure state machine for interactive mic mode. No React, no I/O.
 * Reducer function `transition(state, event)` decides the next state.
 *
 *   OFF ──toggleOn──▶ IDLE_LISTENING ──speechStart──▶ USER_SPEAKING ──silenceCommit──▶ PROCESSING
 *                              ▲                                                          │
 *                              │                                                          │ replyReady
 *                              │ avatarDone                                                ▼
 *                       AVATAR_SPEAKING ◀──────────────────────────────────────────────── (process)
 *
 * From PROCESSING or AVATAR_SPEAKING, a `speechStart` event causes barge-in:
 *   → USER_SPEAKING (the in-flight pipeline is cancelled by the orchestrator).
 *
 * Any state collapses to OFF on `toggleOff` or `fatalError`.
 * Recoverable errors land in IDLE_LISTENING (still on, just nothing happening).
 */

export type InteractiveState =
  | 'OFF'
  | 'IDLE_LISTENING'
  | 'USER_SPEAKING'
  | 'PROCESSING'
  | 'AVATAR_SPEAKING'

export type InteractiveEvent =
  | { type: 'toggleOn' }
  | { type: 'toggleOff' }
  | { type: 'speechStart' }
  | { type: 'silenceCommit' }
  | { type: 'replyReady' }
  | { type: 'avatarDone' }
  | { type: 'recoverableError' }
  | { type: 'fatalError' }

export const HINT_TEXT_BY_STATE: Record<InteractiveState, string> = {
  OFF: '',
  IDLE_LISTENING: 'Waiting for speech...',
  USER_SPEAKING: 'Listening...',
  PROCESSING: 'Thinking about reply...',
  AVATAR_SPEAKING: 'Feel free to interrupt me',
}

export function transition(state: InteractiveState, event: InteractiveEvent): InteractiveState {
  if (event.type === 'fatalError' || event.type === 'toggleOff') return 'OFF'
  if (event.type === 'recoverableError') return state === 'OFF' ? 'OFF' : 'IDLE_LISTENING'

  switch (state) {
    case 'OFF':
      return event.type === 'toggleOn' ? 'IDLE_LISTENING' : state
    case 'IDLE_LISTENING':
      return event.type === 'speechStart' ? 'USER_SPEAKING' : state
    case 'USER_SPEAKING':
      if (event.type === 'silenceCommit') return 'PROCESSING'
      return state
    case 'PROCESSING':
      if (event.type === 'speechStart') return 'USER_SPEAKING'
      if (event.type === 'replyReady') return 'AVATAR_SPEAKING'
      return state
    case 'AVATAR_SPEAKING':
      if (event.type === 'speechStart') return 'USER_SPEAKING'
      if (event.type === 'avatarDone') return 'IDLE_LISTENING'
      return state
  }
}

export function isInteractiveOn(state: InteractiveState): boolean {
  return state !== 'OFF'
}
