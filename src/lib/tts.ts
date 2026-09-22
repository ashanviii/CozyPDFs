/**
 * Listen Mode.
 *
 * The browser's speech engine is asked for one sentence at a time. That costs a
 * little latency between sentences but buys everything that matters: accurate
 * highlighting, instant skip, rate changes that take effect now, and immunity
 * to the ~15s utterance cut-off in Chromium.
 */
import type { Block } from './types'

export interface Sentence {
  /** Index into the document's block list. */
  blockIndex: number
  blockId: string
  /** Character offsets inside the block's text. */
  start: number
  end: number
  text: string
  chapter: number
}

export interface VoiceOption {
  uri: string
  name: string
  lang: string
  /** A short, human label: "Warm · en-GB". */
  label: string
  quality: number
  local: boolean
}

/* ------------------------------------------------------------ sentences ---- */

const ABBREVIATIONS =
  /\b(mr|mrs|ms|dr|prof|sr|jr|st|mt|vs|etc|eg|ie|fig|no|vol|op|ch|pp|approx|dept|univ|inc|ltd|co)\.$/i

/** Splits a block into speakable sentences, keeping offsets into the original. */
export function splitSentences(text: string): { start: number; end: number; text: string }[] {
  const out: { start: number; end: number; text: string }[] = []
  const push = (start: number, end: number) => {
    const slice = text.slice(start, end)
    const lead = slice.length - slice.trimStart().length
    const trimmed = slice.trim()
    if (trimmed) out.push({ start: start + lead, end: start + lead + trimmed.length, text: trimmed })
  }

  const Segmenter = (Intl as { Segmenter?: typeof Intl.Segmenter }).Segmenter
  if (Segmenter) {
    try {
      const segmenter = new Segmenter(undefined, { granularity: 'sentence' })
      for (const segment of segmenter.segment(text)) {
        push(segment.index, segment.index + segment.segment.length)
      }
      if (out.length) return mergeStubs(out)
    } catch {
      /* fall through to the regex splitter */
    }
  }

  let start = 0
  for (let i = 0; i < text.length; i++) {
    const ch = text[i]
    if (ch !== '.' && ch !== '!' && ch !== '?' && ch !== '…') continue
    let end = i + 1
    while (end < text.length && /["'”’)\]]/.test(text[end])) end++
    const next = text[end]
    if (next && next !== ' ' && next !== '\n') continue
    if (ABBREVIATIONS.test(text.slice(Math.max(0, i - 12), i + 1))) continue
    push(start, end)
    start = end
    i = end - 1
  }
  if (start < text.length) push(start, text.length)
  return mergeStubs(out.length ? out : [{ start: 0, end: text.length, text: text.trim() }])
}

/** Glues "1." or "Fig." style fragments onto the sentence that follows. */
function mergeStubs(sentences: { start: number; end: number; text: string }[]) {
  const out: typeof sentences = []
  for (const sentence of sentences) {
    const previous = out[out.length - 1]
    const tiny = sentence.text.length < 4 || !/[a-z\d]/i.test(sentence.text)
    if (previous && (tiny || previous.text.length < 4)) {
      previous.end = sentence.end
      previous.text = `${previous.text} ${sentence.text}`.trim()
    } else out.push({ ...sentence })
  }
  return out
}

/** Flattens a document into the sentence stream Listen Mode walks through. */
export function buildSentences(blocks: Block[]): Sentence[] {
  const out: Sentence[] = []
  for (const block of blocks) {
    if (!block.text) continue // images and other non-text blocks have nothing to speak
    for (const piece of splitSentences(block.text)) {
      out.push({
        blockIndex: block.i,
        blockId: block.id,
        start: piece.start,
        end: piece.end,
        text: piece.text,
        chapter: block.chapter,
      })
    }
  }
  return out
}

/* --------------------------------------------------------------- voices ---- */

const PREMIUM = /natural|neural|enhanced|premium|siri|eloquence/i
const GOOD = /google|microsoft|samantha|daniel|karen|moira|serena|alex|zira|david|aria|guy|jenny|ryan|sonia/i
const ROBOTIC = /espeak|compact|pico|festival|flite|mbrola/i

function scoreVoice(voice: SpeechSynthesisVoice, uiLang: string) {
  let score = 0
  if (PREMIUM.test(voice.name)) score += 60
  if (GOOD.test(voice.name)) score += 25
  if (ROBOTIC.test(voice.name)) score -= 60
  if (voice.lang.toLowerCase().startsWith(uiLang)) score += 30
  else if (voice.lang.toLowerCase().startsWith('en')) score += 10
  if (voice.localService) score += 6 // works offline
  if (voice.default) score += 4
  return score
}

/** Voices arrive asynchronously in most browsers; this waits for them once. */
export function loadVoices(timeout = 2500): Promise<SpeechSynthesisVoice[]> {
  if (typeof speechSynthesis === 'undefined') return Promise.resolve([])
  const existing = speechSynthesis.getVoices()
  if (existing.length) return Promise.resolve(existing)
  return new Promise((resolve) => {
    let settled = false
    const finish = () => {
      if (settled) return
      settled = true
      speechSynthesis.removeEventListener('voiceschanged', finish)
      resolve(speechSynthesis.getVoices())
    }
    speechSynthesis.addEventListener('voiceschanged', finish)
    setTimeout(finish, timeout)
  })
}

const FLAVOURS = ['Warm', 'Clear', 'Soft', 'Bright', 'Steady', 'Calm']

/**
 * Picks a short, high-quality shortlist plus the full list. Browsers expose
 * anywhere from two to two hundred voices; a reader only needs a few good ones.
 */
export function curateVoices(voices: SpeechSynthesisVoice[]): {
  featured: VoiceOption[]
  all: VoiceOption[]
} {
  const uiLang = (navigator.language || 'en').slice(0, 2).toLowerCase()
  const seen = new Set<string>()
  const options: VoiceOption[] = []
  for (const voice of voices) {
    const key = `${voice.name}|${voice.lang}`
    if (seen.has(key)) continue
    seen.add(key)
    options.push({
      uri: voice.voiceURI,
      name: voice.name,
      lang: voice.lang,
      label: voice.name.replace(/\s*\((.*?)\)\s*/g, ' ').replace(/Microsoft |Google /, '').trim(),
      quality: scoreVoice(voice, uiLang),
      local: voice.localService,
    })
  }
  options.sort((a, b) => b.quality - a.quality || a.name.localeCompare(b.name))

  const featured: VoiceOption[] = []
  const usedLabels = new Set<string>()
  for (const option of options) {
    if (featured.length >= 4) break
    const short = option.label.split(/[\s-]/)[0].toLowerCase()
    if (usedLabels.has(short)) continue
    usedLabels.add(short)
    featured.push({ ...option, label: `${FLAVOURS[featured.length]} · ${option.label}` })
  }
  return { featured, all: options }
}

/* --------------------------------------------------------------- engine ---- */

export interface SpeechOptions {
  voiceURI: string | null
  rate: number
  pitch: number
  volume: number
}

interface EngineEvents {
  onSentence?: (index: number, sentence: Sentence) => void
  onChapter?: (chapter: number) => void
  onStateChange?: (state: 'idle' | 'playing' | 'paused') => void
  onEnd?: () => void
  onError?: (message: string) => void
}

export class SpeechEngine {
  private sentences: Sentence[] = []
  private index = 0
  private state: 'idle' | 'playing' | 'paused' = 'idle'
  private options: SpeechOptions = { voiceURI: null, rate: 1, pitch: 1, volume: 1 }
  private voices: SpeechSynthesisVoice[] = []
  private events: EngineEvents = {}
  private current: SpeechSynthesisUtterance | null = null
  private keepAliveTimer: number | null = null
  /** Guards against the `onend` of an utterance we deliberately cancelled. */
  private generation = 0

  static get supported() {
    return typeof window !== 'undefined' && 'speechSynthesis' in window
  }

  async init(events: EngineEvents) {
    this.events = events
    this.voices = await loadVoices()
    return this.voices
  }

  setOptions(options: Partial<SpeechOptions>) {
    const rateChanged = options.rate !== undefined && options.rate !== this.options.rate
    const voiceChanged = options.voiceURI !== undefined && options.voiceURI !== this.options.voiceURI
    this.options = { ...this.options, ...options }
    // Rate and voice only apply to a new utterance, so restart the sentence.
    if ((rateChanged || voiceChanged) && this.state === 'playing') this.speakCurrent()
  }

  setSentences(sentences: Sentence[]) {
    this.sentences = sentences
  }

  get position() {
    return this.index
  }

  get playing() {
    return this.state === 'playing'
  }

  get paused() {
    return this.state === 'paused'
  }

  /** Nearest sentence at or after a block, used when Listen starts mid-page. */
  indexForBlock(blockIndex: number) {
    const found = this.sentences.findIndex((s) => s.blockIndex >= blockIndex)
    return found === -1 ? Math.max(0, this.sentences.length - 1) : found
  }

  play(from?: number) {
    if (!SpeechEngine.supported || !this.sentences.length) return
    if (from !== undefined) this.index = Math.min(Math.max(0, from), this.sentences.length - 1)
    if (this.state === 'paused' && from === undefined) {
      speechSynthesis.resume()
      this.setState('playing')
      this.startKeepAlive()
      return
    }
    this.setState('playing')
    this.startKeepAlive()
    this.speakCurrent()
  }

  pause() {
    if (this.state !== 'playing') return
    // Safari's `pause` is unreliable mid-utterance, so cancel and re-speak the
    // sentence on resume. Chromium keeps the utterance and resumes cleanly.
    this.setState('paused')
    this.stopKeepAlive()
    try {
      speechSynthesis.pause()
    } catch {
      speechSynthesis.cancel()
    }
  }

  toggle() {
    if (this.state === 'playing') this.pause()
    else this.play()
  }

  stop() {
    this.generation++
    this.setState('idle')
    this.stopKeepAlive()
    speechSynthesis.cancel()
    this.current = null
  }

  next() {
    this.jump(1)
  }

  previous() {
    this.jump(-1)
  }

  seek(index: number) {
    this.index = Math.min(Math.max(0, index), Math.max(0, this.sentences.length - 1))
    if (this.state === 'playing') this.speakCurrent()
    else this.emitSentence()
  }

  private jump(delta: number) {
    const next = this.index + delta
    if (next < 0 || next >= this.sentences.length) return
    this.seek(next)
  }

  private setState(state: 'idle' | 'playing' | 'paused') {
    if (this.state === state) return
    this.state = state
    this.events.onStateChange?.(state)
  }

  private emitSentence() {
    const sentence = this.sentences[this.index]
    if (!sentence) return
    this.events.onSentence?.(this.index, sentence)
  }

  private speakCurrent() {
    const sentence = this.sentences[this.index]
    if (!sentence) {
      this.stop()
      this.events.onEnd?.()
      return
    }

    const generation = ++this.generation
    speechSynthesis.cancel()

    const utterance = new SpeechSynthesisUtterance(speakable(sentence.text))
    const voice = this.voices.find((v) => v.voiceURI === this.options.voiceURI)
    if (voice) {
      utterance.voice = voice
      utterance.lang = voice.lang
    }
    utterance.rate = clamp(this.options.rate, 0.5, 3)
    utterance.pitch = clamp(this.options.pitch, 0.5, 1.6)
    utterance.volume = clamp(this.options.volume, 0, 1)

    utterance.onstart = () => {
      if (generation !== this.generation) return
      this.emitSentence()
      const chapter = this.sentences[this.index]?.chapter
      if (chapter !== undefined && chapter !== this.lastChapter) {
        this.lastChapter = chapter
        this.events.onChapter?.(chapter)
      }
    }
    utterance.onend = () => {
      if (generation !== this.generation || this.state !== 'playing') return
      if (this.index + 1 >= this.sentences.length) {
        this.stop()
        this.events.onEnd?.()
        return
      }
      this.index++
      this.speakCurrent() // rolls straight on into the next chapter
    }
    utterance.onerror = (event) => {
      if (generation !== this.generation) return
      // "interrupted"/"canceled" are what our own cancel() looks like.
      if (event.error === 'interrupted' || event.error === 'canceled') return
      this.events.onError?.(describeSpeechError(event.error))
      this.stop()
    }

    this.current = utterance
    // Chromium occasionally drops an utterance queued in the same tick as a
    // cancel; a zero-delay hop is enough to avoid it.
    setTimeout(() => {
      if (generation !== this.generation || this.state !== 'playing') return
      speechSynthesis.speak(utterance)
    }, 0)
  }

  private lastChapter = -1

  /** Chromium stops speaking after ~15s unless it is nudged. */
  private startKeepAlive() {
    this.stopKeepAlive()
    this.keepAliveTimer = window.setInterval(() => {
      if (this.state !== 'playing') return
      if (speechSynthesis.speaking && !speechSynthesis.paused) {
        speechSynthesis.pause()
        speechSynthesis.resume()
      }
    }, 10_000)
  }

  private stopKeepAlive() {
    if (this.keepAliveTimer !== null) {
      clearInterval(this.keepAliveTimer)
      this.keepAliveTimer = null
    }
  }

  dispose() {
    this.stop()
    this.events = {}
  }
}

const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value))

/** Small pronunciation cleanups that stop most engines from stumbling. */
function speakable(text: string) {
  return text
    .replace(/’/g, "'")
    .replace(/[“”]/g, '"')
    .replace(/—/g, ', ')
    .replace(/–/g, '-')
    .replace(/\[\d+(?:[,–-]\s*\d+)*\]/g, '') // citation markers
    .replace(/\bet al\./gi, 'and others')
    .replace(/\bi\.e\./gi, 'that is')
    .replace(/\be\.g\./gi, 'for example')
    .replace(/\bcf\./gi, 'compare')
    .replace(/\bp\.\s?(\d)/gi, 'page $1')
    .replace(/\s+/g, ' ')
    .trim()
}

function describeSpeechError(error: string) {
  switch (error) {
    case 'not-allowed':
      return 'Your browser blocked speech. Tap play once more to allow it.'
    case 'synthesis-unavailable':
    case 'synthesis-failed':
      return 'This voice is unavailable right now. Try another voice.'
    case 'language-unavailable':
    case 'voice-unavailable':
      return 'That voice is no longer installed. Pick another one.'
    case 'audio-busy':
      return 'Something else is using audio. Pause it and try again.'
    default:
      return 'Listening stopped unexpectedly.'
  }
}
