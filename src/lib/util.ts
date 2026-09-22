export const uid = () =>
  typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`

export const clamp = (value: number, min: number, max: number) =>
  Math.min(max, Math.max(min, value))

export function formatBytes(bytes: number) {
  if (!bytes) return '0 KB'
  const units = ['B', 'KB', 'MB', 'GB']
  const index = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)))
  const value = bytes / 1024 ** index
  return `${value >= 10 || index === 0 ? Math.round(value) : value.toFixed(1)} ${units[index]}`
}

export function formatDuration(minutes: number) {
  if (minutes < 1) return 'under a minute'
  if (minutes < 60) return `${Math.round(minutes)} min`
  const hours = Math.floor(minutes / 60)
  const rest = Math.round(minutes % 60)
  if (hours >= 10 || rest === 0) return `${hours} hr`
  return `${hours} hr ${rest} min`
}

const RELATIVE = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' })
const STEPS: [Intl.RelativeTimeFormatUnit, number][] = [
  ['second', 60],
  ['minute', 60],
  ['hour', 24],
  ['day', 7],
  ['week', 4.348],
  ['month', 12],
  ['year', Infinity],
]

export function formatRelative(timestamp?: number) {
  if (!timestamp) return 'never'
  let delta = (timestamp - Date.now()) / 1000
  if (Math.abs(delta) < 45) return 'just now'
  for (const [unit, span] of STEPS) {
    if (Math.abs(delta) < span) return RELATIVE.format(Math.round(delta), unit)
    delta /= span
  }
  return 'a while ago'
}

/** "the-pragmatic-programmer (2nd ed).pdf" -> "The Pragmatic Programmer" */
export function titleFromFileName(fileName: string) {
  const base = fileName.replace(/\.pdf$/i, '').replace(/[_]+/g, ' ')
  const cleaned = base
    .replace(/\s*\(\s*(z-?lib(rary)?(\.org)?|pdfdrive|libgen|annas?[- ]archive)[^)]*\)\s*/gi, ' ')
    .replace(/\b(ebook|epub|pdf|retail|scan|ocr|v\d+(\.\d+)?)\b/gi, ' ')
    .replace(/[-–—]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
  const words = (cleaned || base).split(' ')
  return words
    .map((word) =>
      word.length > 2 && word === word.toLowerCase()
        ? word[0].toUpperCase() + word.slice(1)
        : word,
    )
    .join(' ')
    .slice(0, 160)
}

/** A stable, pleasant hue from any string — used for folder chips. */
export function hueFrom(text: string) {
  let hash = 0
  for (let i = 0; i < text.length; i++) hash = (hash * 31 + text.charCodeAt(i)) | 0
  return Math.abs(hash) % 360
}

export interface Debounced<A extends unknown[]> {
  (...args: A): void
  cancel: () => void
  /** Runs immediately, cancelling any pending call. */
  flush: (...args: A) => void
}

export function debounce<A extends unknown[]>(fn: (...args: A) => void, wait: number): Debounced<A> {
  let timer: number | undefined
  const wrapped = ((...args: A) => {
    window.clearTimeout(timer)
    timer = window.setTimeout(() => fn(...args), wait)
  }) as Debounced<A>
  wrapped.cancel = () => window.clearTimeout(timer)
  wrapped.flush = (...args: A) => {
    window.clearTimeout(timer)
    fn(...args)
  }
  return wrapped
}

export const isTypingTarget = (target: EventTarget | null) => {
  const el = target as HTMLElement | null
  if (!el) return false
  const tag = el.tagName
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || el.isContentEditable
}

/** Formats a count with its noun: 3 books, 1 book. */
export const plural = (count: number, singular: string, pluralForm = `${singular}s`) =>
  `${count} ${count === 1 ? singular : pluralForm}`
