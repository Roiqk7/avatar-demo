import { describe, it, expect, vi, beforeEach } from 'vitest'

const CHROME_UA =
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'

const SAFARI_UA =
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15'

const FIREFOX_UA =
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 14.4; rv:124.0) Gecko/20100101 Firefox/124.0'

describe('isSafari', () => {
  beforeEach(() => {
    vi.resetModules()
  })

  it('returns false for Chrome user agent', async () => {
    vi.stubGlobal('navigator', { userAgent: CHROME_UA })
    const { isSafari } = await import('./browser')
    expect(isSafari).toBe(false)
  })

  it('returns true for Safari user agent', async () => {
    vi.stubGlobal('navigator', { userAgent: SAFARI_UA })
    const { isSafari } = await import('./browser')
    expect(isSafari).toBe(true)
  })

  it('returns false for Firefox', async () => {
    vi.stubGlobal('navigator', { userAgent: FIREFOX_UA })
    const { isSafari } = await import('./browser')
    expect(isSafari).toBe(false)
  })
})
