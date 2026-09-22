import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { Icon } from '../components/Icon'
import { Sheet } from '../components/ui'
import {
  Flow,
  blockElementFor,
  buildSegments,
  chapterStartSet,
  offsetInBlock,
  segmentForBlock,
  topBlockIndex,
  type Range,
} from '../components/reader/Flow'
import {
  ContentsPanel,
  NoteEditor,
  SelectionMenu,
  TunePanel,
  type SelectionState,
} from '../components/reader/panels'
import { ListenBar } from '../components/reader/ListenBar'
import { ScannedView } from '../components/reader/ScannedView'
import { useSettings } from '../state/settings'
import { useLibrary } from '../state/library'
import { useToast } from '../state/toast'
import {
  annotationsFor,
  deleteAnnotation,
  getBook,
  getDoc,
  getFile,
  getProgress,
  putAnnotation,
} from '../lib/db'
import { navigate } from '../lib/router'
import { ambient } from '../lib/ambient'
import { useWakeLock } from '../lib/pwa'
import { SpeechEngine, buildSentences, curateVoices, type Sentence, type VoiceOption } from '../lib/tts'
import { clamp, debounce, formatDuration, isTypingTarget, uid } from '../lib/util'
import type { Annotation, Book, BookDoc, HighlightColor } from '../lib/types'

type Panel = 'none' | 'contents' | 'tune'
type Tab = 'contents' | 'notes' | 'search'

export function ReaderView({ bookId }: { bookId: string }) {
  const { settings, set } = useSettings()
  const { saveProgress, touchBook } = useLibrary()
  const toast = useToast()

  const [book, setBook] = useState<Book | null>(null)
  const [doc, setDoc] = useState<BookDoc | null>(null)
  const [scanData, setScanData] = useState<ArrayBuffer | null>(null)
  const [annotations, setAnnotations] = useState<Annotation[]>([])
  const [status, setStatus] = useState<'loading' | 'ready' | 'missing'>('loading')

  const [blockIndex, setBlockIndex] = useState(0)
  const [percent, setPercent] = useState(0)
  const [segmentIndex, setSegmentIndex] = useState(0)
  const [page, setPage] = useState(0)
  const [pageCount, setPageCount] = useState(1)
  const [scanPage, setScanPage] = useState(1)

  const [immersive, setImmersive] = useState(false)
  const [panel, setPanel] = useState<Panel>('none')
  const [tab, setTab] = useState<Tab>('contents')
  const [selection, setSelection] = useState<SelectionState | null>(null)
  const [editingNote, setEditingNote] = useState<Annotation | null>(null)
  const [flash, setFlash] = useState<{ blockIndex: number; start: number; end: number } | null>(null)
  const [showAmbience, setShowAmbience] = useState(false)

  const [listening, setListening] = useState(false)
  const [ttsPlaying, setTtsPlaying] = useState(false)
  const [activeSentence, setActiveSentence] = useState<Sentence | null>(null)
  const [voices, setVoices] = useState<{ featured: VoiceOption[]; all: VoiceOption[] }>({
    featured: [],
    all: [],
  })

  const scrollRef = useRef<HTMLDivElement>(null)
  const flowRef = useRef<HTMLDivElement>(null)
  const engineRef = useRef<SpeechEngine | null>(null)
  const voicesRef = useRef<{ featured: VoiceOption[]; all: VoiceOption[] }>({ featured: [], all: [] })
  const pendingJump = useRef<number | null>(null)
  const lastScrollTop = useRef(0)
  const restored = useRef(false)

  const blocks = doc?.blocks ?? []
  const chapters = doc?.chapters ?? []
  const isScanned = status === 'ready' && blocks.length === 0

  /* ----------------------------------------------------------- loading -- */

  useEffect(() => {
    let cancelled = false
    restored.current = false
    setStatus('loading')
    setDoc(null)
    setScanData(null)

    void (async () => {
      const found = await getBook(bookId)
      if (cancelled) return
      if (!found || found.deleted) {
        setStatus('missing')
        return
      }
      setBook(found)

      const [loadedDoc, marks, saved, file] = await Promise.all([
        getDoc(bookId),
        annotationsFor(bookId),
        getProgress(bookId),
        getFile(bookId),
      ])
      if (cancelled) return

      if (!file) {
        setStatus('missing')
        return
      }

      setAnnotations(marks)
      if (saved) {
        setBlockIndex(saved.blockIndex)
        setPercent(saved.percent)
        pendingJump.current = saved.blockIndex
      }

      if (loadedDoc && loadedDoc.blocks.length) {
        setDoc(loadedDoc)
      } else {
        setDoc({ bookId, version: 1, blocks: [], chapters: [] })
        setScanData(await file.blob.arrayBuffer())
      }
      setStatus('ready')
      void touchBook(bookId)
    })()

    return () => {
      cancelled = true
    }
  }, [bookId, touchBook])

  /* -------------------------------------------------------- derivations -- */

  const segments = useMemo(() => buildSegments(blocks, chapters), [blocks, chapters])
  const chapterStarts = useMemo(() => chapterStartSet(chapters), [chapters])
  const currentChapter = blocks[blockIndex]?.chapter ?? 0
  const mode = isScanned ? 'scroll' : settings.mode

  const visibleBlocks = useMemo(() => {
    if (mode !== 'page') return blocks
    const segment = segments[Math.min(segmentIndex, segments.length - 1)]
    return segment ? blocks.slice(segment.start, segment.end) : blocks
  }, [blocks, mode, segmentIndex, segments])

  const bookmarks = useMemo(
    () => new Set(annotations.filter((a) => a.kind === 'bookmark').map((a) => a.blockIndex)),
    [annotations],
  )

  const rangesByBlock = useMemo(() => {
    const map = new Map<number, Range[]>()
    const add = (index: number, range: Range) => {
      const list = map.get(index)
      if (list) list.push(range)
      else map.set(index, [range])
    }
    for (const mark of annotations) {
      if (mark.kind === 'bookmark') continue
      add(mark.blockIndex, {
        start: mark.start,
        end: mark.end,
        className: `hl--${mark.color}${mark.note ? ' has-note' : ''}`,
        id: mark.id,
      })
    }
    if (flash) {
      add(flash.blockIndex, {
        start: flash.start,
        end: flash.end,
        className: 'search-hit is-current',
      })
    }
    if (activeSentence) {
      add(activeSentence.blockIndex, {
        start: activeSentence.start,
        end: activeSentence.end,
        className: 'sentence-live',
      })
    }
    for (const block of blocks) {
      if (block.links) {
        for (const link of block.links) {
          add(block.i, { start: link.start, end: link.end, className: '', href: link.href, page: link.page })
        }
      }
      if (block.strong) {
        for (const run of block.strong) {
          add(block.i, { start: run.start, end: run.end, className: '', strong: true })
        }
      }
    }
    return map
  }, [annotations, flash, activeSentence, blocks])

  const sentences = useMemo(() => buildSentences(blocks), [blocks])

  const layoutKey = [
    settings.font,
    settings.fontSize,
    settings.lineHeight,
    settings.measure,
    settings.margin,
    settings.paragraphSpacing,
    settings.justify,
  ].join('|')

  const minutesLeft = book ? book.minutes * (1 - percent) : 0

  // Switching between scroll and pages should land on the same paragraph.
  useEffect(() => {
    if (status !== 'ready') return
    pendingJump.current = blockIndex
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode])

  /* ------------------------------------------------------ progress save -- */

  const persist = useMemo(
    () =>
      debounce((next: { blockIndex: number; percent: number }) => {
        void getProgress(bookId).then((previous) =>
          saveProgress({
            bookId,
            blockIndex: next.blockIndex,
            percent: next.percent,
            furthest: Math.max(previous?.furthest ?? 0, next.percent),
            updatedAt: Date.now(),
          }),
        )
      }, 900),
    [bookId, saveProgress],
  )

  useEffect(() => {
    if (status !== 'ready') return
    persist({ blockIndex, percent })
  }, [blockIndex, percent, persist, status])

  // The latest position, readable from listeners that must not re-subscribe on
  // every scroll tick.
  const positionRef = useRef({ blockIndex, percent })
  positionRef.current = { blockIndex, percent }

  // Flush the position when the reader is left or the tab is hidden.
  useEffect(() => {
    const flush = () => persist.flush(positionRef.current)
    window.addEventListener('pagehide', flush)
    document.addEventListener('visibilitychange', flush)
    return () => {
      window.removeEventListener('pagehide', flush)
      document.removeEventListener('visibilitychange', flush)
      flush()
    }
  }, [persist])

  /* ------------------------------------------------------------ scroll -- */

  const onScanPage = useCallback((number: number, total: number) => {
    setScanPage(number)
    setPercent(number / Math.max(1, total))
  }, [])

  const onScroll = useCallback(() => {
    const scroller = scrollRef.current
    const flow = flowRef.current
    if (!scroller || !flow || mode === 'page') return

    const top = scroller.scrollTop
    const span = Math.max(1, scroller.scrollHeight - scroller.clientHeight)
    setPercent(clamp(top / span, 0, 1))
    setBlockIndex(topBlockIndex(flow, top))

    // Chrome gets out of the way on the way down, and comes back on the way up.
    const delta = top - lastScrollTop.current
    if (Math.abs(delta) > 36) {
      setImmersive(delta > 0 && top > 120)
      lastScrollTop.current = top
    }
  }, [mode])

  /* ------------------------------------------------- jumping & restoring -- */

  const goToBlock = useCallback(
    (index: number, mark?: { start: number; end: number }) => {
      const target = clamp(index, 0, Math.max(0, blocks.length - 1))
      setBlockIndex(target)
      pendingJump.current = target
      if (mark) {
        setFlash({ blockIndex: target, ...mark })
        window.setTimeout(() => setFlash(null), 2600)
      }
      if (mode === 'page') setSegmentIndex(segmentForBlock(segments, target))
    },
    [blocks.length, mode, segments],
  )

  useLayoutEffect(() => {
    const target = pendingJump.current
    if (target === null || status !== 'ready') return
    const flow = flowRef.current
    const scroller = scrollRef.current
    if (!flow || !scroller) return

    const element = flow.querySelector<HTMLElement>(`[data-block="${target}"]`)
    if (!element) {
      if (mode === 'page') setSegmentIndex(segmentForBlock(segments, target))
      return // the right segment will render next tick
    }

    if (mode === 'page') {
      const width = flow.clientWidth
      const gap = parseFloat(getComputedStyle(flow).columnGap || '56') || 56
      if (width > 0) {
        setPage(Math.max(0, Math.round(element.offsetLeft / (width + gap))))
        pendingJump.current = null
      }
    } else {
      const previous = scroller.style.scrollBehavior
      if (!restored.current) scroller.style.scrollBehavior = 'auto'
      // Clear the top bar so a jumped-to heading is never tucked underneath it.
      scroller.scrollTo({ top: target === 0 ? 0 : Math.max(0, element.offsetTop - 88) })
      scroller.style.scrollBehavior = previous
      pendingJump.current = null
      restored.current = true
    }
  })

  // Percent follows the page cursor in paginated mode.
  useEffect(() => {
    if (mode !== 'page' || !blocks.length) return
    const segment = segments[segmentIndex]
    if (!segment) return
    const within = pageCount > 1 ? page / (pageCount - 1) : 0
    const index = Math.round(segment.start + (segment.end - segment.start - 1) * within)
    setBlockIndex(clamp(index, 0, blocks.length - 1))
    setPercent(clamp(index / Math.max(1, blocks.length - 1), 0, 1))
  }, [blocks.length, mode, page, pageCount, segmentIndex, segments])

  const turnPage = useCallback(
    (delta: number) => {
      if (mode !== 'page') {
        const scroller = scrollRef.current
        if (!scroller) return
        scroller.scrollBy({ top: delta * (scroller.clientHeight - 64), behavior: 'smooth' })
        return
      }
      const next = page + delta
      if (next >= 0 && next < pageCount) {
        setPage(next)
        return
      }
      const nextSegment = segmentIndex + delta
      if (nextSegment < 0 || nextSegment >= segments.length) return
      setSegmentIndex(nextSegment)
      // Landing backwards should show the last page of the previous segment.
      setPage(delta < 0 ? Number.MAX_SAFE_INTEGER : 0)
    },
    [mode, page, pageCount, segmentIndex, segments.length],
  )

  // Clamp the "last page" sentinel once the new segment has been measured.
  useEffect(() => {
    if (page > pageCount - 1) setPage(Math.max(0, pageCount - 1))
  }, [page, pageCount])

  /* -------------------------------------------------------- annotations -- */

  const reloadAnnotations = useCallback(async () => {
    setAnnotations(await annotationsFor(bookId))
  }, [bookId])

  const readSelection = useCallback((): SelectionState | null => {
    const active = window.getSelection()
    if (!active || active.isCollapsed || !active.rangeCount) return null
    const range = active.getRangeAt(0)
    const flow = flowRef.current
    if (!flow || !flow.contains(range.commonAncestorContainer)) return null

    const startBlock = blockElementFor(range.startContainer)
    const endBlock = blockElementFor(range.endContainer)
    if (!startBlock || !endBlock) return null

    const first = Number(startBlock.dataset.block)
    const last = Number(endBlock.dataset.block)
    const pieces: SelectionState['pieces'] = []

    if (first === last) {
      const start = offsetInBlock(startBlock, range.startContainer, range.startOffset)
      const end = offsetInBlock(endBlock, range.endContainer, range.endOffset)
      if (end <= start) return null
      pieces.push({ blockIndex: first, start, end, text: blocks[first]?.text.slice(start, end) ?? '' })
    } else {
      const from = Math.min(first, last)
      const to = Math.max(first, last)
      for (let index = from; index <= to; index++) {
        const text = blocks[index]?.text ?? ''
        const start =
          index === first ? offsetInBlock(startBlock, range.startContainer, range.startOffset) : 0
        const end = index === last ? offsetInBlock(endBlock, range.endContainer, range.endOffset) : text.length
        if (end > start) pieces.push({ blockIndex: index, start, end, text: text.slice(start, end) })
      }
    }
    if (!pieces.length) return null

    const rect = range.getBoundingClientRect()
    const marked = (range.startContainer.parentElement as HTMLElement | null)?.closest('mark')
    return {
      x: clamp(rect.left + rect.width / 2, 120, window.innerWidth - 120),
      y: Math.max(64, rect.top - 10),
      pieces,
      text: pieces.map((piece) => piece.text).join(' '),
      annotationId: marked?.dataset.annotation,
    }
  }, [blocks])

  useEffect(() => {
    if (status !== 'ready' || isScanned) return
    const onUp = () => {
      window.setTimeout(() => setSelection(readSelection()), 10)
    }
    const onDown = (event: MouseEvent) => {
      if ((event.target as HTMLElement).closest('.selection-menu')) return
      setSelection(null)
    }
    document.addEventListener('mouseup', onUp)
    document.addEventListener('touchend', onUp)
    document.addEventListener('mousedown', onDown)
    return () => {
      document.removeEventListener('mouseup', onUp)
      document.removeEventListener('touchend', onUp)
      document.removeEventListener('mousedown', onDown)
    }
  }, [isScanned, readSelection, status])

  const highlight = useCallback(
    async (color: HighlightColor, note?: string) => {
      if (!selection) return
      const now = Date.now()
      const created: Annotation[] = selection.pieces.map((piece, index) => ({
        id: uid(),
        bookId,
        kind: note ? 'note' : 'highlight',
        blockId: `b${piece.blockIndex}`,
        blockIndex: piece.blockIndex,
        start: piece.start,
        end: piece.end,
        text: piece.text,
        note: index === 0 ? note : undefined,
        color,
        createdAt: now,
        updatedAt: now,
      }))
      for (const annotation of created) await putAnnotation(annotation)
      await reloadAnnotations()
      window.getSelection()?.removeAllRanges()
      setSelection(null)
      set('highlightColor', color)
      return created[0]
    },
    [bookId, reloadAnnotations, selection, set],
  )

  const toggleBookmark = useCallback(async () => {
    const existing = annotations.find((a) => a.kind === 'bookmark' && a.blockIndex === blockIndex)
    if (existing) {
      await deleteAnnotation(existing.id)
      toast('Bookmark removed.', 'info')
    } else {
      const now = Date.now()
      await putAnnotation({
        id: uid(),
        bookId,
        kind: 'bookmark',
        blockId: `b${blockIndex}`,
        blockIndex,
        start: 0,
        end: 0,
        text: blocks[blockIndex]?.text.slice(0, 120) ?? '',
        color: settings.highlightColor,
        createdAt: now,
        updatedAt: now,
      })
      toast('Bookmarked.', 'success')
    }
    await reloadAnnotations()
  }, [annotations, blockIndex, blocks, bookId, reloadAnnotations, settings.highlightColor, toast])

  const onFlowClick = useCallback(
    (event: React.MouseEvent) => {
      const link = (event.target as HTMLElement).closest('a.inline-link') as HTMLElement | null
      if (link) {
        const targetPage = link.dataset.page ? Number(link.dataset.page) : undefined
        if (targetPage) {
          // An internal link carries no real href (it would collide with the
          // app's own hash router), so the jump is entirely our own doing.
          event.preventDefault()
          const target = blocks.find((b) => b.page >= targetPage) ?? blocks[blocks.length - 1]
          if (target) goToBlock(target.i)
        }
        // An external link has a real href and target="_blank" — the browser
        // handles it natively, including ctrl/cmd-click and "open in new tab".
        return
      }

      const mark = (event.target as HTMLElement).closest('[data-annotation]')
      const id = (mark as HTMLElement | null)?.dataset.annotation
      if (id) {
        const found = annotations.find((annotation) => annotation.id === id)
        if (found) {
          setEditingNote(found)
          return
        }
      }
      // A tap in the middle of the page toggles the chrome.
      if (window.getSelection()?.isCollapsed !== false) {
        setImmersive((value) => !value)
      }
    },
    [annotations, blocks, goToBlock],
  )

  /* ------------------------------------------------------------- listen -- */

  const ensureEngine = useCallback(async () => {
    if (engineRef.current) return engineRef.current
    const engine = new SpeechEngine()
    const available = await engine.init({
      onSentence: (_, sentence) => {
        setActiveSentence(sentence)
        setBlockIndex(sentence.blockIndex)
      },
      onStateChange: (state) => setTtsPlaying(state === 'playing'),
      onEnd: () => {
        setTtsPlaying(false)
        setActiveSentence(null)
        toast('That is the end of the book.', 'success')
      },
      onError: (message) => toast(message, 'error'),
    })
    const curated = curateVoices(available)
    voicesRef.current = curated
    setVoices(curated)
    engineRef.current = engine
    return engine
  }, [toast])

  const startListening = useCallback(
    async (fromBlock?: number) => {
      if (!SpeechEngine.supported) {
        toast('This browser has no speech engine, so Listen Mode is unavailable.', 'error')
        return
      }
      if (!sentences.length) {
        toast('There is no text to read aloud in this book.', 'warn')
        return
      }
      const engine = await ensureEngine()
      engine.setSentences(sentences)
      // First run: adopt the best voice this device has instead of the default.
      const picked = settings.voiceURI ?? voicesRef.current.featured[0]?.uri ?? null
      if (!settings.voiceURI && picked) set('voiceURI', picked)
      engine.setOptions({
        voiceURI: picked,
        rate: settings.rate,
        pitch: settings.pitch,
        volume: settings.ttsVolume,
      })
      setListening(true)
      engine.play(engine.indexForBlock(fromBlock ?? blockIndex))
    },
    [blockIndex, ensureEngine, sentences, set, settings.pitch, settings.rate, settings.ttsVolume, settings.voiceURI, toast],
  )

  const stopListening = useCallback(() => {
    engineRef.current?.stop()
    setListening(false)
    setTtsPlaying(false)
    setActiveSentence(null)
  }, [])

  useEffect(() => () => engineRef.current?.dispose(), [])

  // Live settings changes reach the engine mid-sentence.
  useEffect(() => {
    engineRef.current?.setOptions({
      rate: settings.rate,
      pitch: settings.pitch,
      volume: settings.ttsVolume,
      voiceURI: settings.voiceURI,
    })
  }, [settings.pitch, settings.rate, settings.ttsVolume, settings.voiceURI])

  // Keep the spoken sentence on screen.
  useEffect(() => {
    if (!activeSentence || !flowRef.current || !scrollRef.current) return
    const flow = flowRef.current
    const element = flow.querySelector<HTMLElement>(`[data-block="${activeSentence.blockIndex}"]`)
    if (!element) {
      if (mode === 'page') setSegmentIndex(segmentForBlock(segments, activeSentence.blockIndex))
      else pendingJump.current = activeSentence.blockIndex
      return
    }
    if (mode === 'page') {
      const width = flow.clientWidth
      const gap = parseFloat(getComputedStyle(flow).columnGap || '56') || 56
      const target = Math.max(0, Math.round(element.offsetLeft / (width + gap)))
      if (target !== page) setPage(target)
      return
    }
    const scroller = scrollRef.current
    const top = element.offsetTop - scroller.scrollTop
    if (top < 80 || top > scroller.clientHeight - 140) {
      scroller.scrollTo({ top: Math.max(0, element.offsetTop - scroller.clientHeight * 0.34) })
    }
  }, [activeSentence, mode, page, segments])

  useWakeLock(listening && ttsPlaying && settings.keepAwake)

  /* ------------------------------------------------------------ ambience -- */

  useEffect(() => {
    // play() handles 'none' by stopping, and keeps the player's idea of the
    // current scene in step with the setting.
    void ambient.play(settings.ambience)
  }, [settings.ambience])

  useEffect(() => {
    ambient.setVolume(settings.ambienceVolume)
  }, [settings.ambienceVolume])

  useEffect(() => () => ambient.stop(), [])

  // Browsers hold audio until the reader interacts; pick it up on first touch.
  useEffect(() => {
    if (settings.ambience === 'none') return
    const kick = () => {
      void ambient.play(settings.ambience)
      window.removeEventListener('pointerdown', kick)
      window.removeEventListener('keydown', kick)
    }
    window.addEventListener('pointerdown', kick)
    window.addEventListener('keydown', kick)
    return () => {
      window.removeEventListener('pointerdown', kick)
      window.removeEventListener('keydown', kick)
    }
  }, [settings.ambience])

  /* ----------------------------------------------------------- keyboard -- */

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (isTypingTarget(event.target) || event.metaKey || event.ctrlKey || event.altKey) return
      switch (event.key) {
        case 'ArrowRight':
        case 'PageDown':
          event.preventDefault()
          turnPage(1)
          break
        case 'ArrowLeft':
        case 'PageUp':
          event.preventDefault()
          turnPage(-1)
          break
        case ' ':
          if (listening) {
            event.preventDefault()
            engineRef.current?.toggle()
          }
          break
        case 'Home':
          event.preventDefault()
          goToBlock(0)
          break
        case 'End':
          event.preventDefault()
          goToBlock(blocks.length - 1)
          break
        case 'Escape':
          if (panel !== 'none') setPanel('none')
          else if (immersive) setImmersive(false)
          else navigate({ name: 'library', folderId: null })
          break
        case 'f':
          setImmersive((value) => !value)
          break
        case 'b':
          void toggleBookmark()
          break
        case 'c':
          setTab('contents')
          setPanel('contents')
          break
        case 'n':
          setTab('notes')
          setPanel('contents')
          break
        case '/':
          event.preventDefault()
          setTab('search')
          setPanel('contents')
          break
        case 't':
          setPanel((value) => (value === 'tune' ? 'none' : 'tune'))
          break
        case 'l':
          if (listening) stopListening()
          else void startListening()
          break
        default:
          break
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [blocks.length, goToBlock, immersive, listening, panel, startListening, stopListening, toggleBookmark, turnPage])

  /* -------------------------------------------------------------- views -- */

  if (status === 'loading') {
    return (
      <div className="boot">
        <span className="spinner" />
        Opening your book…
      </div>
    )
  }

  if (status === 'missing') {
    return (
      <div className="boot" style={{ textAlign: 'center', padding: 24 }}>
        <Icon name="alert" size={28} />
        <p style={{ maxWidth: '38ch', lineHeight: 1.6 }}>
          {book
            ? `"${book.title}" is in your library, but its PDF is not on this device. Add the file here to read it.`
            : 'That book is no longer in your library.'}
        </p>
        <a className="btn btn--outline" href="#/library">
          Back to library
        </a>
      </div>
    )
  }

  const chapterTitle = chapters[currentChapter]?.title ?? book?.title ?? ''
  const sourcePageCount = book?.pageCount ?? 0
  const sourcePage = isScanned ? scanPage : (blocks[blockIndex]?.page ?? 1)

  return (
    <div
      className={`reader${immersive ? ' is-immersive' : ''}${listening ? ' is-listening' : ''}`}
    >
      <header className="reader__bar reader__bar--top">
        <a className="icon-btn" href="#/library" aria-label="Back to library">
          <Icon name="arrowLeft" size={19} />
        </a>
        <span className="reader__title">{book?.title}</span>

        <button
          type="button"
          className="icon-btn"
          aria-label="Contents, notes and search"
          onClick={() => {
            setTab('contents')
            setPanel('contents')
          }}
        >
          <Icon name="list" size={19} />
        </button>
        <button
          type="button"
          className="icon-btn"
          aria-label="Search in book"
          onClick={() => {
            setTab('search')
            setPanel('contents')
          }}
        >
          <Icon name="search" size={19} />
        </button>
        <button
          type="button"
          className="icon-btn"
          aria-label="Bookmark this spot"
          aria-pressed={bookmarks.has(blockIndex)}
          onClick={() => void toggleBookmark()}
        >
          <Icon name="bookmark" size={19} fill={bookmarks.has(blockIndex)} />
        </button>
        <button
          type="button"
          className={`icon-btn${settings.ambience !== 'none' ? ' is-on' : ''}`}
          aria-label="Ambient sound"
          onClick={() => setShowAmbience(true)}
        >
          <Icon name="wind" size={19} />
        </button>
        {!isScanned && (
          <>
            <button
              type="button"
              className="icon-btn"
              aria-label="Reading settings"
              onClick={() => setPanel('tune')}
            >
              <Icon name="type" size={19} />
            </button>
            <button
              type="button"
              className={`icon-btn${listening ? ' is-on' : ''}`}
              aria-label="Listen mode"
              onClick={() => (listening ? stopListening() : void startListening())}
            >
              <Icon name="headphones" size={19} />
            </button>
          </>
        )}
      </header>

      <div
        className="reader__scroll"
        data-mode={mode}
        ref={scrollRef}
        onScroll={onScroll}
        onClick={onFlowClick}
      >
        {isScanned && scanData ? (
          <ScannedView data={scanData} scrollRef={scrollRef} onPage={onScanPage} />
        ) : (
          <Flow
            blocks={visibleBlocks}
            chapterStarts={chapterStarts}
            rangesByBlock={rangesByBlock}
            bookmarks={bookmarks}
            liveBlock={activeSentence?.blockIndex ?? null}
            mode={mode}
            page={page}
            onPageCount={setPageCount}
            flowRef={flowRef}
            layoutKey={layoutKey}
          />
        )}
      </div>

      {mode === 'page' && (
        <>
          <button
            type="button"
            className="tap-zone tap-zone--prev"
            aria-label="Previous page"
            onClick={() => turnPage(-1)}
          />
          <button
            type="button"
            className="tap-zone tap-zone--next"
            aria-label="Next page"
            onClick={() => turnPage(1)}
          />
        </>
      )}

      <div className="progress-rail" aria-hidden="true">
        <i style={{ width: `${percent * 100}%` }} />
      </div>

      <footer className="reader__bar reader__bar--bottom">
        <span className="reader__chapter">{chapterTitle}</span>
        <span className="reader__dot">·</span>
        <span>
          {mode === 'page' && !isScanned
            ? `page ${page + 1} of ${pageCount}`
            : `p${sourcePage} of ${sourcePageCount}`}
        </span>
        <span className="reader__dot">·</span>
        <span>{Math.round(percent * 100)}%</span>
        {!isScanned && minutesLeft > 1 && (
          <>
            <span className="reader__dot">·</span>
            <span className="left-chip">{formatDuration(minutesLeft)} left</span>
          </>
        )}
      </footer>

      {selection && (
        <SelectionMenu
          selection={selection}
          onHighlight={(color) => void highlight(color)}
          onNote={() =>
            void highlight(settings.highlightColor).then((created) => {
              if (created) setEditingNote(created)
            })
          }
          onCopy={() => {
            void navigator.clipboard
              ?.writeText(selection.text)
              .then(() => toast('Copied.', 'success'))
              .catch(() => toast('Your browser blocked the clipboard.', 'warn'))
            setSelection(null)
          }}
          onListen={() => {
            const from = selection.pieces[0].blockIndex
            setSelection(null)
            window.getSelection()?.removeAllRanges()
            void startListening(from)
          }}
          onRemove={() => {
            if (!selection.annotationId) return
            void deleteAnnotation(selection.annotationId).then(reloadAnnotations)
            setSelection(null)
          }}
        />
      )}

      {listening && (
        <ListenBar
          playing={ttsPlaying}
          sentenceText={activeSentence?.text ?? ''}
          chapterTitle={chapterTitle}
          voices={voices}
          onToggle={() => engineRef.current?.toggle()}
          onPrevious={() => engineRef.current?.previous()}
          onNext={() => engineRef.current?.next()}
          onClose={stopListening}
        />
      )}

      <TunePanel open={panel === 'tune'} onClose={() => setPanel('none')} />

      <ContentsPanel
        open={panel === 'contents'}
        onClose={() => setPanel('none')}
        tab={tab}
        onTab={setTab}
        chapters={chapters}
        blocks={blocks}
        currentChapter={currentChapter}
        annotations={annotations}
        onJump={goToBlock}
        onEditNote={setEditingNote}
        onDeleteAnnotation={(id) => void deleteAnnotation(id).then(reloadAnnotations)}
      />

      <NoteEditor
        annotation={editingNote}
        onClose={() => setEditingNote(null)}
        onSave={(note, color) => {
          if (!editingNote) return
          void putAnnotation({
            ...editingNote,
            note: note.trim() || undefined,
            kind: note.trim() ? 'note' : 'highlight',
            color,
            updatedAt: Date.now(),
          }).then(reloadAnnotations)
          setEditingNote(null)
        }}
        onDelete={() => {
          if (!editingNote) return
          void deleteAnnotation(editingNote.id).then(reloadAnnotations)
          setEditingNote(null)
        }}
      />

      <AmbienceSheet open={showAmbience} onClose={() => setShowAmbience(false)} />
    </div>
  )
}

/* Ambient sound is available while reading silently too, not just in Listen. */
function AmbienceSheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { settings, set } = useSettings()
  return (
    <Sheet open={open} onClose={onClose} title="Ambient sound">
      <div className="sheet__body">
        <div className="font-row">
          {[
            ['none', 'Silence', 'No background sound'],
            ['rain', 'Rain', 'Steady rain on a window'],
            ['fireplace', 'Fireplace', 'A low fire, crackling'],
            ['cafe', 'Café', 'Distant chatter and cups'],
            ['forest', 'Forest', 'Wind in leaves, birdsong'],
          ].map(([id, name, hint]) => (
            <button
              key={id}
              type="button"
              className="font-option"
              aria-pressed={settings.ambience === id}
              onClick={() => set('ambience', id as never)}
            >
              <Icon name={id === 'none' ? 'volumeOff' : 'wind'} size={16} />
              <span className="font-option__name">{name}</span>
              <span className="font-option__note">{hint}</span>
            </button>
          ))}
        </div>
        <label className="tune__label" htmlFor="ambience-volume">
          <span>Volume</span>
          <span className="tune__value">{Math.round((settings.ambienceVolume / 0.8) * 100)}%</span>
        </label>
        <input
          id="ambience-volume"
          className="slider"
          type="range"
          min={0}
          max={0.8}
          step={0.02}
          value={settings.ambienceVolume}
          onChange={(event) => set('ambienceVolume', Number(event.target.value))}
        />
      </div>
    </Sheet>
  )
}
