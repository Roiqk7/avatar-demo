import { describe, it, expect } from 'vitest'
import { detectSlur } from './slurFilter'

describe('detectSlur', () => {
  it('returns null for clean text', () => {
    expect(detectSlur('Hello, how are you?')).toBeNull()
    expect(detectSlur('')).toBeNull()
    expect(detectSlur('   ')).toBeNull()
  })

  it('detects English slurs (exact word match)', () => {
    const result = detectSlur('you are a fuck')
    expect(result).not.toBeNull()
    expect(result?.language).toBe('en')
  })

  it('detects Czech slurs', () => {
    const result = detectSlur('ty cigan blbý')
    expect(result).not.toBeNull()
    expect(result?.language).toBe('cs')
  })

  it('detects Czech prefix matches (kokot*)', () => {
    const result = detectSlur('to je kokote')
    expect(result).not.toBeNull()
    expect(result?.language).toBe('cs')
  })

  it('is case-insensitive', () => {
    expect(detectSlur('FUCK this')).not.toBeNull()
    expect(detectSlur('Fuck this')).not.toBeNull()
  })

  it('normalises punctuation separators', () => {
    // b-a-d would not match, but "shit" with surrounding punctuation should
    expect(detectSlur('what the shit!')).not.toBeNull()
  })

  it('returns language of the matched term', () => {
    const csResult = detectSlur('cigan')
    expect(csResult?.language).toBe('cs')

    const enResult = detectSlur('fuck')
    expect(enResult?.language).toBe('en')
  })

  it('returns matched term', () => {
    const result = detectSlur('this is shit')
    expect(typeof result?.matched).toBe('string')
    expect(result!.matched.length).toBeGreaterThan(0)
  })

  it('checks Czech before English (deterministic order)', () => {
    // "negr" is a Czech term; should be detected as cs
    const result = detectSlur('negr')
    expect(result?.language).toBe('cs')
  })

  it('matches ascii czech terms (diacritics stripped by normalizer)', () => {
    // The normaliser replaces non-ASCII chars with spaces, so the ascii
    // variant must be used for matching to work.
    expect(detectSlur('cigan')).not.toBeNull()
    expect(detectSlur('cigani')).not.toBeNull()
  })
})
