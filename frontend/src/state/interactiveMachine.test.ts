import { describe, it, expect } from 'vitest'
import { transition } from './interactiveMachine'
import type { InteractiveState, InteractiveEvent } from './interactiveMachine'

function t(state: InteractiveState, event: InteractiveEvent['type']): InteractiveState {
  return transition(state, { type: event } as InteractiveEvent)
}

describe('interactiveMachine', () => {
  it('OFF + toggleOn → IDLE_LISTENING', () => {
    expect(t('OFF', 'toggleOn')).toBe('IDLE_LISTENING')
  })

  it('OFF + speechStart → OFF (no-op)', () => {
    expect(t('OFF', 'speechStart')).toBe('OFF')
  })

  it('IDLE_LISTENING + speechStart → USER_SPEAKING', () => {
    expect(t('IDLE_LISTENING', 'speechStart')).toBe('USER_SPEAKING')
  })

  it('USER_SPEAKING + silenceCommit → PROCESSING', () => {
    expect(t('USER_SPEAKING', 'silenceCommit')).toBe('PROCESSING')
  })

  it('PROCESSING + replyReady → AVATAR_SPEAKING', () => {
    expect(t('PROCESSING', 'replyReady')).toBe('AVATAR_SPEAKING')
  })

  it('AVATAR_SPEAKING + avatarDone → IDLE_LISTENING', () => {
    expect(t('AVATAR_SPEAKING', 'avatarDone')).toBe('IDLE_LISTENING')
  })

  it('full happy-path cycle', () => {
    let s: InteractiveState = 'OFF'
    s = transition(s, { type: 'toggleOn' })
    expect(s).toBe('IDLE_LISTENING')
    s = transition(s, { type: 'speechStart' })
    expect(s).toBe('USER_SPEAKING')
    s = transition(s, { type: 'silenceCommit' })
    expect(s).toBe('PROCESSING')
    s = transition(s, { type: 'replyReady' })
    expect(s).toBe('AVATAR_SPEAKING')
    s = transition(s, { type: 'avatarDone' })
    expect(s).toBe('IDLE_LISTENING')
  })

  it('barge-in: speechStart from PROCESSING → USER_SPEAKING', () => {
    expect(t('PROCESSING', 'speechStart')).toBe('USER_SPEAKING')
  })

  it('barge-in: speechStart from AVATAR_SPEAKING → USER_SPEAKING', () => {
    expect(t('AVATAR_SPEAKING', 'speechStart')).toBe('USER_SPEAKING')
  })

  it('fatalError collapses any state to OFF', () => {
    const states: InteractiveState[] = ['OFF', 'IDLE_LISTENING', 'USER_SPEAKING', 'PROCESSING', 'AVATAR_SPEAKING']
    for (const s of states) {
      expect(t(s, 'fatalError')).toBe('OFF')
    }
  })

  it('toggleOff collapses any state to OFF', () => {
    const states: InteractiveState[] = ['IDLE_LISTENING', 'USER_SPEAKING', 'PROCESSING', 'AVATAR_SPEAKING']
    for (const s of states) {
      expect(t(s, 'toggleOff')).toBe('OFF')
    }
  })

  it('recoverableError from OFF stays OFF', () => {
    expect(t('OFF', 'recoverableError')).toBe('OFF')
  })

  it('recoverableError from active state → IDLE_LISTENING', () => {
    expect(t('USER_SPEAKING', 'recoverableError')).toBe('IDLE_LISTENING')
    expect(t('PROCESSING', 'recoverableError')).toBe('IDLE_LISTENING')
    expect(t('AVATAR_SPEAKING', 'recoverableError')).toBe('IDLE_LISTENING')
  })

  it('unknown events on IDLE_LISTENING leave state unchanged', () => {
    expect(t('IDLE_LISTENING', 'silenceCommit')).toBe('IDLE_LISTENING')
    expect(t('IDLE_LISTENING', 'replyReady')).toBe('IDLE_LISTENING')
    expect(t('IDLE_LISTENING', 'avatarDone')).toBe('IDLE_LISTENING')
  })
})
