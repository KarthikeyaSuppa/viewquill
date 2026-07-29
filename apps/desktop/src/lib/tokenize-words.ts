/**
 * Shared word-tokenizer used by both the manuscript reader (see
 * `components/draft/manuscript-reader.tsx`) and the speech/read-aloud feature, so both agree
 * exactly on how text is split into words and character offsets. Any run of non-whitespace is
 * a "word" — whitespace (space, tab, newline) is always the separator. `matchAll` on a global
 * regex hands back each match's `.index`, which is exactly the character offset of that word's
 * first character within the string being scanned — no manual counting/approximation, so this
 * can't drift out of sync with the raw text.
 *
 * This MUST stay in lockstep with the `WORD_RE = /\S+/g` logic in `manuscript-reader.tsx` —
 * do not change the regex here without changing it there too (and vice versa).
 */

const WORD_RE = /\S+/g

export interface WordToken {
  word: string
  start: number
  end: number
}

export function tokenizeWords(text: string): WordToken[] {
  const tokens: WordToken[] = []
  for (const match of text.matchAll(WORD_RE)) {
    const start = match.index ?? 0
    tokens.push({
      word: match[0],
      start,
      end: start + match[0].length,
    })
  }
  return tokens
}
