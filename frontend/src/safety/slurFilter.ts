export type SlurLanguage = 'en' | 'cs'

function normalizeForMatching(text: string): string {
  const s = (text || '').normalize('NFKC').toLowerCase()
  // Replace punctuation/separators with spaces and collapse runs.
  return s.replace(/[\s\W_]+/gu, ' ').trim()
}

function compileTerms(terms: string[]): Set<string> {
  return new Set(terms.map(t => t.trim().toLowerCase()).filter(Boolean))
}

function compilePrefixes(prefixes: string[]): string[] {
  return prefixes.map(p => p.trim().toLowerCase()).filter(Boolean)
}

// Keep this list curated and small (demo-grade, not a moderation system).
// Note: We intentionally include common profanity because the UX treats it as "be kind".
const TERMS_BY_LANG: Record<SlurLanguage, Set<string>> = {
  en: compileTerms([
    'nigger',
    'nigga',
    'faggot',
    'fag',
    'retard',
    'spic',
    'kike',
    'chink',
    'gook',
    'tranny',
    'fuck',
    'fucking',
    'fucked',
    'fucker',
    'shit',
    'shitty',
    'cunt',
    'bitch',
    'bastard',
  ]),
  cs: compileTerms([
    'cigan',
    'cigán',
    'cigani',
    'cigáni',
    'negr',
    'buzna',
    'buzerant',
    'teplouš',
    'cikán',
    'cikani',
    'cikáni',
  ]),
}

const PREFIXES_BY_LANG: Record<SlurLanguage, string[]> = {
  en: compilePrefixes([]),
  // Inflections: kokot, kokote, kokotko, ...
  cs: compilePrefixes(['kokot']),
}

export type SlurDetection = {
  language: SlurLanguage
  matched: string
}

export function detectSlur(text: string): SlurDetection | null {
  const normalized = normalizeForMatching(text)
  if (!normalized) return null

  const words = normalized.split(' ')
  // Deterministic: check Czech first, then English.
  for (const lang of ['cs', 'en'] as const) {
    const dict = TERMS_BY_LANG[lang]
    const prefixes = PREFIXES_BY_LANG[lang]
    for (const w of words) {
      if (dict.has(w)) return { language: lang, matched: w }
      for (const p of prefixes) {
        if (w.startsWith(p)) return { language: lang, matched: w }
      }
    }
  }
  return null
}

