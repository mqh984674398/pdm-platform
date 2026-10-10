/** Approximate glyph advance in em: CJK is full-width, Latin text averages ~0.56em in IBM Plex Sans. */
function advance(ch: string): number {
  return /[⺀-鿿＀-￯]/.test(ch) ? 1 : /[A-Z0-9]/.test(ch) ? 0.62 : 0.53
}

export function textWidth(text: string, fontSize: number): number {
  let em = 0
  for (const ch of text) em += advance(ch)
  return em * fontSize
}

/**
 * Break a label into at most `maxLines` lines that fit `width` at `fontSize`.
 * Latin text breaks at spaces, CJK between characters; the last line is ellipsized if needed.
 */
export function fitLines(text: string, width: number, fontSize: number, maxLines = 2): string[] {
  if (textWidth(text, fontSize) <= width) return [text]
  const tokens = /\s/.test(text) ? text.split(/\s+/) : [...text]
  const sep = /\s/.test(text) ? ' ' : ''
  const lines: string[] = []
  let cur = ''
  for (const tok of tokens) {
    const next = cur ? cur + sep + tok : tok
    if (cur && textWidth(next, fontSize) > width) {
      lines.push(cur)
      cur = tok
    } else {
      cur = next
    }
  }
  lines.push(cur)
  if (lines.length > maxLines) {
    lines.splice(maxLines - 1, lines.length, lines.slice(maxLines - 1).join(sep))
  }
  const last = lines.length - 1
  while (textWidth(lines[last]!, fontSize) > width && lines[last]!.length > 1) {
    lines[last] = lines[last]!.replace(/.(…)?$/u, '') + '…'
  }
  return lines
}
