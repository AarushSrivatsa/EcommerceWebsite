export function countWords(text: string): number {
  const t = text.trim()
  return t ? t.split(/\s+/).length : 0
}

/** 135 -> "2m 15s" */
export function formatDuration(totalSeconds: number): string {
  const s = Math.max(0, Math.round(totalSeconds))
  const m = Math.floor(s / 60)
  const r = s % 60
  if (m === 0) return `${r}s`
  return r === 0 ? `${m}m` : `${m}m ${r}s`
}

export function speakingSeconds(words: number, wordsPerMinute: number): number {
  return wordsPerMinute > 0 ? (words / wordsPerMinute) * 60 : 0
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
}
