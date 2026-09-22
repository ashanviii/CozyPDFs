import { memo, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import type { Block, Chapter } from '../../lib/types'

/** A styled run of characters inside a block: highlight, search hit, sentence, link. */
export interface Range {
  start: number
  end: number
  className: string
  /** Annotation id, so a click can open the right note. */
  id?: string
  /** Set for a link to an external URL — rendered as a real, clickable anchor. */
  href?: string
  /** Set for a link to elsewhere in the book (1-based source page). */
  page?: number
  /** Set for a glossary term's bold lead-in. */
  strong?: boolean
}

const EMPTY: Range[] = []

/**
 * Splits a block's text at every range boundary so overlapping highlights,
 * search hits and the live sentence can all coexist on the same words.
 */
function paint(text: string, ranges: Range[]): ReactNode {
  if (!ranges.length) return text

  const clipped = ranges
    .map((range) => ({
      ...range,
      start: Math.max(0, Math.min(text.length, range.start)),
      end: Math.max(0, Math.min(text.length, range.end)),
    }))
    .filter((range) => range.end > range.start)
  if (!clipped.length) return text

  const cuts = new Set<number>([0, text.length])
  for (const range of clipped) {
    cuts.add(range.start)
    cuts.add(range.end)
  }
  const points = [...cuts].sort((a, b) => a - b)

  const out: ReactNode[] = []
  for (let i = 0; i < points.length - 1; i++) {
    const from = points[i]
    const to = points[i + 1]
    if (to <= from) continue
    const slice = text.slice(from, to)
    const covering = clipped.filter((range) => range.start <= from && range.end >= to)
    if (!covering.length) {
      out.push(slice)
      continue
    }
    const annotationId = covering.find((range) => range.id)?.id
    const link = covering.find((range) => range.href || range.page !== undefined)
    const isStrong = covering.some((range) => range.strong)
    const boldStyle = isStrong ? { fontWeight: 600 } : undefined
    const className = covering.map((range) => range.className).join(' ').trim()

    if (link) {
      // A real `href` for an external URL (so ctrl/cmd-click and "open in new
      // tab" work for free); an internal jump carries no href at all, since a
      // real one would collide with the app's own hash router.
      out.push(
        <a
          key={from}
          className={`inline-link${className ? ` ${className}` : ''}`}
          style={boldStyle}
          data-annotation={annotationId}
          data-page={link.page}
          href={link.href}
          target={link.href ? '_blank' : undefined}
          rel={link.href ? 'noopener noreferrer' : undefined}
        >
          {slice}
        </a>,
      )
      continue
    }

    if (className) {
      out.push(
        <mark key={from} className={className} style={boldStyle} data-annotation={annotationId}>
          {slice}
        </mark>,
      )
      continue
    }

    if (isStrong) {
      out.push(<strong key={from}>{slice}</strong>)
      continue
    }

    out.push(slice)
  }
  return out
}

const TAGS: Record<Exclude<Block['type'], 'image' | 'code' | 'table'>, keyof JSX.IntrinsicElements> = {
  h1: 'h2',
  h2: 'h3',
  h3: 'h4',
  p: 'p',
  quote: 'blockquote',
  list: 'p',
  caption: 'p',
}

interface BlockProps {
  block: Block
  ranges: Range[]
  chapterStart: boolean
  bookmarked: boolean
  live: boolean
}

const BlockView = memo(function BlockView({
  block,
  ranges,
  chapterStart,
  bookmarked,
  live,
}: BlockProps) {
  const className = [
    `b-${block.type}`,
    chapterStart ? 'is-chapter-start' : '',
    bookmarked ? 'is-bookmarked' : '',
    live ? 'block-live' : '',
  ]
    .filter(Boolean)
    .join(' ')

  if (block.type === 'image') {
    return (
      <figure className={className} data-block={block.i} id={`block-${block.i}`}>
        <img
          src={block.src}
          alt=""
          loading="lazy"
          width={block.width}
          height={block.height}
          style={block.width && block.height ? { aspectRatio: `${block.width} / ${block.height}` } : undefined}
        />
      </figure>
    )
  }

  if (block.type === 'code') {
    return (
      <pre className={className} data-block={block.i} id={`block-${block.i}`}>
        <code>{paint(block.text, ranges)}</code>
      </pre>
    )
  }

  if (block.type === 'table') {
    const rows = block.rows ?? []
    const headRow = block.tableHeader ? (rows[0] ?? null) : null
    const bodyRows = block.tableHeader ? rows.slice(1) : rows
    return (
      <div className={className} data-block={block.i} id={`block-${block.i}`}>
        <div className="table-scroll">
          <table>
            {headRow && (
              <thead>
                <tr>
                  {headRow.map((cell, index) => (
                    <th key={index}>{cell}</th>
                  ))}
                </tr>
              </thead>
            )}
            <tbody>
              {bodyRows.map((row, rowIndex) => (
                <tr key={rowIndex}>
                  {row.map((cell, cellIndex) => (
                    <td key={cellIndex}>{cell}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    )
  }

  const Tag = TAGS[block.type]
  return (
    <Tag className={className} data-block={block.i} id={`block-${block.i}`} data-indent={block.indent}>
      {paint(block.text, ranges)}
    </Tag>
  )
})

/* ----------------------------------------------------------------- flow -- */

interface FlowProps {
  blocks: Block[]
  chapterStarts: Set<number>
  rangesByBlock: Map<number, Range[]>
  bookmarks: Set<number>
  liveBlock: number | null
  mode: 'scroll' | 'page'
  /** Page index inside the current segment, for paginated mode. */
  page: number
  onPageCount: (count: number) => void
  flowRef: React.RefObject<HTMLDivElement>
  /** Changes whenever typography does, so pages are re-counted. */
  layoutKey: string
}

export function Flow({
  blocks,
  chapterStarts,
  rangesByBlock,
  bookmarks,
  liveBlock,
  mode,
  page,
  onPageCount,
  flowRef,
  layoutKey,
}: FlowProps) {
  const viewportRef = useRef<HTMLDivElement>(null)
  const [metrics, setMetrics] = useState({ width: 0, gap: 56 })

  // Paginated mode lays the text out in columns exactly one viewport wide,
  // then slides the whole column strip sideways — the classic ebook trick.
  useLayoutEffect(() => {
    if (mode !== 'page') return
    const viewport = viewportRef.current
    const flow = flowRef.current
    if (!viewport || !flow) return

    const measure = () => {
      const width = viewport.clientWidth
      if (!width) return
      const gap = Math.max(32, Math.min(72, Math.round(width * 0.09)))
      setMetrics({ width, gap })
      // Let the new column geometry apply before counting pages.
      requestAnimationFrame(() => {
        const total = flow.scrollWidth
        const count = Math.max(1, Math.round((total + gap) / (width + gap)))
        onPageCount(count)
      })
    }

    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(viewport)
    return () => observer.disconnect()
  }, [mode, blocks, flowRef, onPageCount, layoutKey])

  const children = useMemo(
    () =>
      blocks.map((block) => (
        <BlockView
          key={block.id}
          block={block}
          ranges={rangesByBlock.get(block.i) ?? EMPTY}
          chapterStart={chapterStarts.has(block.i)}
          bookmarked={bookmarks.has(block.i)}
          live={liveBlock === block.i}
        />
      )),
    [blocks, rangesByBlock, chapterStarts, bookmarks, liveBlock],
  )

  if (mode === 'page') {
    return (
      <div className="page-viewport" ref={viewportRef}>
        <div
          className="flow"
          data-mode="page"
          ref={flowRef}
          style={{
            width: metrics.width || undefined,
            columnWidth: metrics.width || undefined,
            columnGap: metrics.gap,
            transform: `translateX(-${page * (metrics.width + metrics.gap)}px)`,
          }}
        >
          {children}
        </div>
      </div>
    )
  }

  return (
    <div className="flow" data-mode="scroll" ref={flowRef}>
      {children}
    </div>
  )
}

/* ------------------------------------------------------------ utilities -- */

/** Character offset of a DOM point inside its block element. */
export function offsetInBlock(blockEl: HTMLElement, node: Node, offset: number) {
  const walker = document.createTreeWalker(blockEl, NodeFilter.SHOW_TEXT)
  let total = 0
  let current = walker.nextNode()
  while (current) {
    if (current === node) return total + offset
    total += current.textContent?.length ?? 0
    current = walker.nextNode()
  }
  // The point sits on an element boundary rather than in a text node.
  return node.contains(blockEl) || blockEl.contains(node) ? total : 0
}

export const blockElementFor = (node: Node | null): HTMLElement | null => {
  let element = node instanceof HTMLElement ? node : node?.parentElement ?? null
  while (element && !element.dataset.block) element = element.parentElement
  return element
}

/** Chapter boundaries, so the first block of a chapter can get a rule above. */
export function chapterStartSet(chapters: Chapter[]) {
  return new Set(chapters.map((chapter) => chapter.blockIndex))
}

/**
 * Splits a book into paginatable segments. Pagination restarts at each
 * chapter — as a printed book does — and long chapters are chunked so the
 * browser never has to lay out thousands of elements in one column strip.
 */
export function buildSegments(blocks: Block[], chapters: Chapter[], maxBlocks = 220) {
  const segments: { start: number; end: number; chapter: number }[] = []
  if (!blocks.length) return segments

  const bounds = chapters.length ? chapters.map((chapter) => chapter.blockIndex) : [0]
  for (let c = 0; c < bounds.length; c++) {
    const start = bounds[c]
    const end = c + 1 < bounds.length ? bounds[c + 1] : blocks.length
    if (end <= start) continue
    for (let from = start; from < end; from += maxBlocks) {
      segments.push({ start: from, end: Math.min(end, from + maxBlocks), chapter: c })
    }
  }
  return segments.length ? segments : [{ start: 0, end: blocks.length, chapter: 0 }]
}

export function segmentForBlock(
  segments: { start: number; end: number }[],
  blockIndex: number,
) {
  for (let i = 0; i < segments.length; i++) {
    if (blockIndex < segments[i].end) return i
  }
  return Math.max(0, segments.length - 1)
}

/** Finds the top-most block currently in view, by binary search over layout. */
export function topBlockIndex(flow: HTMLElement, scrollTop: number) {
  const children = flow.children
  if (!children.length) return 0
  let low = 0
  let high = children.length - 1
  let best = 0
  const probe = scrollTop + 8
  while (low <= high) {
    const mid = (low + high) >> 1
    const element = children[mid] as HTMLElement
    if (element.offsetTop <= probe) {
      best = mid
      low = mid + 1
    } else high = mid - 1
  }
  const element = children[best] as HTMLElement
  return Number(element.dataset.block ?? best)
}
