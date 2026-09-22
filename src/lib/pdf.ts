/**
 * Turns a PDF into a reflowable document.
 *
 * PDFs have no notion of a paragraph — only glyphs at coordinates. So we walk
 * the text layer, rebuild lines from baselines, work out the column layout,
 * drop running heads, and stitch lines back into paragraphs using typographic
 * cues (indents, gaps, hyphenation, font size). The result is a flat list of
 * blocks that can be laid out at any width, like an ebook.
 *
 * Two more passes ride along with the text: link annotations are mapped onto
 * character ranges inside the blocks they fall under, and embedded images are
 * cropped out of a one-time page render and inserted as their own blocks in
 * reading order, alongside the text.
 */
import * as pdfjs from 'pdfjs-dist'
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'
import type { Block, BlockType, Chapter, LinkSpan } from './types'

pdfjs.GlobalWorkerOptions.workerSrc = workerUrl

export interface ExtractResult {
  blocks: Block[]
  chapters: Chapter[]
  pageCount: number
  wordCount: number
  title: string
  author: string
  cover?: string
  scanned: boolean
}

export type ExtractPhase = 'opening' | 'reading' | 'shaping' | 'cover' | 'done'

export interface ExtractProgress {
  phase: ExtractPhase
  done: number
  total: number
}

interface Line {
  text: string
  x0: number
  x1: number
  y: number
  size: number
  page: number
  /** The PDF's internal resource key for this line's dominant font. Not a
   *  real font name (pdf.js only exposes a synthetic id via its public API),
   *  but a stable enough fingerprint to tell "styled differently from the
   *  surrounding body text" from "the same font as everything else". */
  font: string
  /** Every glyph on this line comes from a monospace (code) font. */
  mono: boolean
  /** Reading-order rank within the page (handles multi-column layouts). */
  band: number
  /** Clickable ranges inside `text`, in this line's own character offsets. */
  links?: LinkSpan[]
  /** Set when this "line" is really a picture standing in the text flow. */
  image?: { src: string; width: number; height: number }
}

const BULLET = /^\s*(?:[•▪◦‣·*]|[-–—]\s|\(?\d{1,2}[.)]\s|[a-z][.)]\s)/i
const CHAPTERISH =
  /^\s*(chapter|part|section|appendix|prologue|epilogue|introduction|preface|foreword|conclusion|abstract|references|bibliography|acknowledg)/i
const PAGE_NUMBERISH = /^\s*(page\s*)?[ivxlcdm\d]{1,6}\s*(\/\s*\d+)?\s*$/i
const CLOSES = /[.!?"”’)]$/
// A trailing hyphen with nothing before it but a letter is a word broken
// across the line — a bare "-" or "–" preceded by a space is a dash or a
// minus sign and must survive intact (this matters most in formulas, where
// stripping it silently changes the expression).
const HYPHEN_END = /[a-z][-‐­]$/i

/* ------------------------------------------------------------ utilities ---- */

const median = (xs: number[]) => {
  if (!xs.length) return 0
  const s = [...xs].sort((a, b) => a - b)
  return s[Math.floor(s.length / 2)]
}

/**
 * The single most common value, not the middle of the sorted list — right
 * for a left margin. Indentation splits its votes across several distinct
 * depths (110, 136, 162…), so even where *most* lines are indented, no one
 * indent level typically outweighs the single outer margin that ordinary
 * paragraphs all share; the median can drift onto an indent level where the
 * mode won't.
 */
const modeOf = (xs: number[], bucket = 1) => {
  if (!xs.length) return 0
  const weights = new Map<number, number>()
  for (const x of xs) {
    const key = Math.round(x / bucket) * bucket
    weights.set(key, (weights.get(key) ?? 0) + 1)
  }
  let best = xs[0]
  let bestWeight = -1
  for (const [key, weight] of weights) {
    if (weight > bestWeight) {
      best = key
      bestWeight = weight
    }
  }
  return best
}

/** Weighted mode, bucketed to 0.5pt — the size most of the *text* is set in. */
function bodySizeOf(lines: Line[]) {
  const weights = new Map<number, number>()
  for (const line of lines) {
    const key = Math.round(line.size * 2) / 2
    weights.set(key, (weights.get(key) ?? 0) + line.text.length)
  }
  let best = 12
  let bestWeight = -1
  for (const [size, weight] of weights) {
    if (weight > bestWeight) {
      best = size
      bestWeight = weight
    }
  }
  return best || 12
}

const normalizeRunningHead = (s: string) =>
  s.replace(/\d+/g, '#').replace(/\s+/g, ' ').trim().toLowerCase()

const yieldToPaint = () => new Promise<void>((resolve) => setTimeout(resolve, 0))

/** Reading order within a page: top-to-bottom, honouring column bands. */
const compareLines = (a: Line, b: Line) => a.band - b.band || b.y - a.y || a.x0 - b.x0

/* --------------------------------------------------------------- links ---- */

interface PageLinkRect {
  x0: number
  y0: number
  x1: number
  y1: number
  href?: string
  page?: number
}

/**
 * pdf.js hands back one item per text-showing run — often a whole sentence,
 * not one item per word — with no per-character positions. To still map a
 * link rect onto the right substring, this treats the run's width as spread
 * evenly across its characters and returns the character range that falls
 * inside the horizontal overlap with the rect (only called once the run's
 * baseline is already known to sit inside the rect's vertical span).
 */
function linkRangesForPiece(
  links: PageLinkRect[],
  piece: { str: string; x: number; w: number },
  y: number,
): { start: number; end: number; href?: string; page?: number }[] {
  const length = piece.str.length
  if (!length || piece.w <= 0) return []
  const out: { start: number; end: number; href?: string; page?: number }[] = []
  for (const link of links) {
    if (y < link.y0 || y > link.y1) continue
    const overlapStart = Math.max(piece.x, link.x0)
    const overlapEnd = Math.min(piece.x + piece.w, link.x1)
    if (overlapEnd <= overlapStart) continue
    const start = Math.max(0, Math.min(length, Math.round(((overlapStart - piece.x) / piece.w) * length)))
    const end = Math.max(0, Math.min(length, Math.round(((overlapEnd - piece.x) / piece.w) * length)))
    if (end > start) out.push({ start, end, href: link.href, page: link.page })
  }
  return out
}

/** Clips, sorts, and merges touching same-target spans into clean ranges. */
function mergeLinkSpans(spans: LinkSpan[], textLength: number): LinkSpan[] | undefined {
  const clipped = spans
    .map((s) => ({ ...s, start: Math.max(0, Math.min(textLength, s.start)), end: Math.max(0, Math.min(textLength, s.end)) }))
    .filter((s) => s.end > s.start)
    .sort((a, b) => a.start - b.start)
  const merged: LinkSpan[] = []
  for (const span of clipped) {
    const prev = merged[merged.length - 1]
    if (prev && prev.href === span.href && prev.page === span.page && span.start - prev.end <= 1) {
      prev.end = Math.max(prev.end, span.end)
    } else {
      merged.push({ ...span })
    }
  }
  return merged.length ? merged : undefined
}

/**
 * Reads a page's link annotations and resolves each to either an external URL
 * or a 1-based page number, in the same coordinate space as the text layer.
 */
async function readPageLinks(
  pdf: pdfjs.PDFDocumentProxy,
  page: pdfjs.PDFPageProxy,
): Promise<PageLinkRect[]> {
  let annotations: Awaited<ReturnType<typeof page.getAnnotations>>
  try {
    annotations = await page.getAnnotations({ intent: 'display' })
  } catch {
    return []
  }
  if (!annotations.length) return []

  const out: PageLinkRect[] = []
  for (const annotation of annotations) {
    if (annotation.subtype !== 'Link') continue
    const rect = annotation.rect as number[] | undefined
    if (!rect || rect.length < 4 || rect.some((n) => !Number.isFinite(n))) continue
    const [rx0, ry0, rx1, ry1] = rect
    const box = { x0: Math.min(rx0, rx1), y0: Math.min(ry0, ry1), x1: Math.max(rx0, rx1), y1: Math.max(ry0, ry1) }

    const url =
      (annotation.url as string | undefined) ?? (annotation.unsafeUrl as string | undefined)
    if (url && /^https?:\/\//i.test(url)) {
      out.push({ ...box, href: url })
      continue
    }

    const rawDest = annotation.dest as string | unknown[] | null | undefined
    if (!rawDest) continue
    try {
      const dest = typeof rawDest === 'string' ? await pdf.getDestination(rawDest) : rawDest
      const ref = Array.isArray(dest) ? dest[0] : null
      if (ref && typeof ref === 'object') {
        const pageIndex = await pdf.getPageIndex(ref as never)
        out.push({ ...box, page: pageIndex + 1 })
      }
    } catch {
      /* one broken destination just means this link is inert, not the page */
    }
  }
  return out
}

/* ---------------------------------------------------------------- lines ---- */

interface RawItem {
  str: string
  transform: number[]
  width: number
  fontName?: string
}

/** pdf.js's per-page `getTextContent()` companion: generic family per font key. */
type PageStyles = Record<string, { fontFamily?: string } | undefined>

function itemsToLines(
  items: RawItem[],
  page: number,
  pageWidth: number,
  pageLinks: PageLinkRect[],
  styles: PageStyles,
): Line[] {
  interface Piece {
    str: string
    x: number
    y: number
    w: number
    size: number
    font: string
  }
  const pieces: Piece[] = []
  for (const item of items) {
    if (!item.str || !item.str.trim()) continue
    const t = item.transform
    const size = Math.hypot(t[2], t[3]) || Math.hypot(t[0], t[1]) || 12
    pieces.push({ str: item.str, x: t[4], y: t[5], w: item.width, size, font: item.fontName ?? '' })
  }
  if (!pieces.length) return []

  // Baselines first, then left-to-right inside each baseline.
  pieces.sort((a, b) => b.y - a.y || a.x - b.x)

  const lines: Line[] = []
  let bucket: Piece[] = []
  let bucketY = pieces[0].y

  const flush = () => {
    if (!bucket.length) return
    bucket.sort((a, b) => a.x - b.x)
    const size = median(bucket.map((p) => p.size))
    let text = ''
    let cursor = -Infinity

    // Link ranges are computed at piece granularity as the text is built, so
    // their offsets land exactly where each piece ends up in the final string.
    const runs: LinkSpan[] = []

    for (const piece of bucket) {
      const gap = piece.x - cursor
      if (text && gap > size * 0.16 && !/\s$/.test(text) && !/^\s/.test(piece.str)) text += ' '
      const pieceStart = text.length
      text += piece.str
      cursor = piece.x + piece.w

      if (pageLinks.length) {
        for (const hit of linkRangesForPiece(pageLinks, piece, bucketY)) {
          runs.push({ start: pieceStart + hit.start, end: pieceStart + hit.end, href: hit.href, page: hit.page })
        }
      }
    }

    // Collapsing whitespace can only ever remove leading characters in
    // practice (pieces are joined with at most one space) — shift for that.
    const collapsed = text.replace(/\s+/g, ' ')
    const lead = collapsed.length - collapsed.trimStart().length
    text = collapsed.trim()

    if (text) {
      // The font key that covers the most characters on this line — a
      // reasonable single "what font is this line" answer even when a line
      // mixes a few glyphs of another face (e.g. a lone italic word).
      const weights = new Map<string, number>()
      for (const piece of bucket) weights.set(piece.font, (weights.get(piece.font) ?? 0) + piece.str.length)
      let font = bucket[0].font
      let fontWeight = -1
      for (const [key, weight] of weights) {
        if (weight > fontWeight) {
          font = key
          fontWeight = weight
        }
      }

      const links = runs.length
        ? mergeLinkSpans(
            runs.map((r) => ({ ...r, start: r.start - lead, end: r.end - lead })),
            text.length,
          )
        : undefined
      lines.push({
        text,
        x0: bucket[0].x,
        x1: cursor,
        y: bucketY,
        size,
        page,
        font,
        // Every piece has to be monospace, not just one — otherwise a single
        // inline `code word` in an ordinary sentence would turn its whole
        // line, and every line like it, into a false-positive code block.
        mono: bucket.every((p) => styles[p.font]?.fontFamily === 'monospace'),
        band: 0,
        links,
      })
    }
    bucket = []
  }

  for (const piece of pieces) {
    const tolerance = Math.max(1.2, piece.size * 0.45)
    if (bucket.length && Math.abs(piece.y - bucketY) > tolerance) {
      flush()
      bucketY = piece.y
    }
    if (!bucket.length) bucketY = piece.y
    bucket.push(piece)
  }
  flush()

  assignReadingBands(lines, pageWidth)
  lines.sort(compareLines)
  return lines
}

/**
 * Detects a two-column layout and assigns each line a band so that sorting
 * yields true reading order: anything above the columns, then the left column,
 * then the right, then anything below.
 */
function assignReadingBands(lines: Line[], pageWidth: number) {
  if (lines.length < 8 || !pageWidth) return
  const mid = pageWidth / 2
  const gutter = pageWidth * 0.04
  const left = lines.filter((l) => l.x1 < mid + gutter)
  const right = lines.filter((l) => l.x0 > mid - gutter)
  const spanning = lines.filter((l) => l.x0 < mid - gutter && l.x1 > mid + gutter)
  const isTwoColumn =
    left.length >= 5 && right.length >= 5 && spanning.length <= Math.max(2, lines.length * 0.12)
  if (!isTwoColumn) return

  const columnLines = [...left, ...right]
  const columnTop = Math.max(...columnLines.map((l) => l.y))
  const columnBottom = Math.min(...columnLines.map((l) => l.y))
  for (const line of lines) {
    const spans = line.x0 < mid - gutter && line.x1 > mid + gutter
    if (spans) line.band = line.y > columnTop ? 0 : line.y < columnBottom ? 3 : 1.5
    else line.band = line.x0 > mid - gutter ? 2 : 1
  }
}

/* --------------------------------------------------------------- images ---- */

type Matrix = [number, number, number, number, number, number]
const IDENTITY: Matrix = [1, 0, 0, 1, 0, 0]

const multiplyMatrix = (a: Matrix, b: Matrix): Matrix => [
  a[0] * b[0] + a[2] * b[1],
  a[1] * b[0] + a[3] * b[1],
  a[0] * b[2] + a[2] * b[3],
  a[1] * b[2] + a[3] * b[3],
  a[0] * b[4] + a[2] * b[5] + a[4],
  a[1] * b[4] + a[3] * b[5] + a[5],
]

const applyMatrix = (m: Matrix, x: number, y: number): [number, number] => [
  m[0] * x + m[2] * y + m[4],
  m[1] * x + m[3] * y + m[5],
]

interface ImageBox {
  x0: number
  y0: number
  x1: number
  y1: number
  area: number
}

/**
 * Walks a page's operator list tracking the graphics-state matrix, and
 * records the page-space bounding box of every painted image. PDF images are
 * always painted into the unit square under the current transform, so the
 * box is just that square's four corners mapped through the matrix.
 */
async function findImageBoxes(page: pdfjs.PDFPageProxy, pageWidth: number, pageHeight: number) {
  let opList: { fnArray: number[]; argsArray: unknown[] }
  try {
    opList = await page.getOperatorList()
  } catch {
    return [] as ImageBox[]
  }

  const OPS = pdfjs.OPS
  const boxes: ImageBox[] = []
  const stack: Matrix[] = []
  let ctm: Matrix = IDENTITY
  // Skip decorative rules, bullets and icons — a real figure is at least a
  // few percent of the page in both dimensions.
  const minSize = Math.min(pageWidth, pageHeight) * 0.045
  const pageArea = pageWidth * pageHeight

  for (let i = 0; i < opList.fnArray.length; i++) {
    const fn = opList.fnArray[i]
    switch (fn) {
      case OPS.save:
      case OPS.paintFormXObjectBegin: {
        stack.push(ctm)
        const args = opList.argsArray[i] as unknown[] | undefined
        const matrix = args?.[0] as number[] | undefined
        if (Array.isArray(matrix) && matrix.length === 6) ctm = multiplyMatrix(ctm, matrix as Matrix)
        break
      }
      case OPS.restore:
      case OPS.paintFormXObjectEnd:
        ctm = stack.pop() ?? IDENTITY
        break
      case OPS.transform: {
        const args = opList.argsArray[i] as number[]
        ctm = multiplyMatrix(ctm, args as Matrix)
        break
      }
      case OPS.paintImageXObject:
      case OPS.paintImageMaskXObject:
      case OPS.paintInlineImageXObject: {
        const corners = [
          applyMatrix(ctm, 0, 0),
          applyMatrix(ctm, 1, 0),
          applyMatrix(ctm, 0, 1),
          applyMatrix(ctm, 1, 1),
        ]
        const xs = corners.map((c) => c[0])
        const ys = corners.map((c) => c[1])
        const x0 = Math.min(...xs)
        const x1 = Math.max(...xs)
        const y0 = Math.min(...ys)
        const y1 = Math.max(...ys)
        const w = x1 - x0
        const h = y1 - y0
        const area = w * h
        // Guard against a runaway matrix (a malformed PDF) producing a box
        // bigger than the page itself.
        if (w >= minSize && h >= minSize && area <= pageArea * 1.05 && Number.isFinite(area)) {
          boxes.push({ x0, y0, x1, y1, area })
        }
        break
      }
      default:
        break
    }
  }
  return boxes
}

/**
 * Drops boxes that are almost entirely inside a bigger one — a logo or badge
 * layered on top of a background photo, not a separate figure worth its own
 * block. Without this, a designed cover turns into a stack of near-duplicate
 * crops of the same artwork.
 */
function dedupeImageBoxes(boxes: ImageBox[]): ImageBox[] {
  const sorted = [...boxes].sort((a, b) => b.area - a.area)
  const kept: ImageBox[] = []
  for (const box of sorted) {
    const swallowed = kept.some((bigger) => {
      const ix0 = Math.max(box.x0, bigger.x0)
      const iy0 = Math.max(box.y0, bigger.y0)
      const ix1 = Math.min(box.x1, bigger.x1)
      const iy1 = Math.min(box.y1, bigger.y1)
      const overlap = Math.max(0, ix1 - ix0) * Math.max(0, iy1 - iy0)
      return overlap / box.area > 0.75
    })
    if (!swallowed) kept.push(box)
  }
  return kept
}

/**
 * Some pages aren't prose at all — a cover, a part-divider, a full-page
 * diagram, a title page with art behind the type. Reflowing those tears the
 * design apart: headline words become stray paragraphs, and the artwork
 * itself gets carved into whichever overlapping XObjects happen to compose
 * it. This recognises that case so the page can be kept exactly as it looked
 * instead, as one picture.
 */
function assessGraphicPage(lines: Line[], imageBoxes: ImageBox[], pageWidth: number, pageHeight: number) {
  if (!imageBoxes.length) return false
  const pageArea = pageWidth * pageHeight
  if (!pageArea) return false

  const imageArea = Math.min(pageArea, imageBoxes.reduce((sum, box) => sum + box.area, 0))
  const coverage = imageArea / pageArea

  const words = lines.reduce(
    (sum, l) => sum + (l.image ? 0 : l.text.split(/\s+/).filter(Boolean).length),
    0,
  )

  let overlapping = 0
  let textLines = 0
  for (const line of lines) {
    if (line.image) continue
    textLines++
    const lineWidth = Math.max(1, line.x1 - line.x0)
    const overlapsArt = imageBoxes.some((box) => {
      if (line.y < box.y0 || line.y > box.y1) return false
      const ix0 = Math.max(line.x0, box.x0)
      const ix1 = Math.min(line.x1, box.x1)
      return Math.max(0, ix1 - ix0) / lineWidth > 0.25
    })
    if (overlapsArt) overlapping++
  }
  const overlapFraction = textLines ? overlapping / textLines : 0

  // Artwork covering most of the page with little real prose — a cover, a
  // divider, a full-bleed illustration.
  const imageDominant = coverage > 0.5 && words < 140
  // Text deliberately laid over or beside art rather than flowing around it —
  // a stylised title page, a labelled diagram, an infographic.
  const textOverArt = coverage > 0.12 && overlapFraction > 0.3

  return imageDominant || textOverArt
}

/** Renders a page whole, for the "keep this page as it looked" path. */
async function renderWholePage(page: pdfjs.PDFPageProxy, targetWidth: number, quality: number) {
  const base = page.getViewport({ scale: 1 })
  const viewport = page.getViewport({ scale: Math.min(2.4, targetWidth / base.width) })
  const canvas = document.createElement('canvas')
  canvas.width = Math.max(1, Math.round(viewport.width))
  canvas.height = Math.max(1, Math.round(viewport.height))
  const context = canvas.getContext('2d', { alpha: false })
  if (!context) return null
  context.fillStyle = '#ffffff'
  context.fillRect(0, 0, canvas.width, canvas.height)
  try {
    await page.render({ canvasContext: context, viewport }).promise
  } catch {
    canvas.width = 0
    canvas.height = 0
    return null
  }
  const src = canvas.toDataURL('image/jpeg', quality)
  const width = canvas.width
  const height = canvas.height
  canvas.width = 0
  canvas.height = 0
  return { src, width, height }
}

const MAX_IMAGE_WIDTH = 860
const MAX_IMAGES_PER_PAGE = 6
const MAX_IMAGE_BYTES = 900_000
const MAX_WHOLE_PAGE_BYTES = 1_400_000

interface FoundImage {
  box: ImageBox
  src: string
  width: number
  height: number
}

/**
 * Crops each qualifying image out of a single render of the page. Rendering
 * (not decoding the XObject directly) is what lets this handle every
 * colour space and filter pdf.js supports, for free.
 */
async function extractPageImages(
  page: pdfjs.PDFPageProxy,
  boxes: ImageBox[],
  budget: { count: number; bytes: number },
): Promise<FoundImage[]> {
  if (!boxes.length || budget.count <= 0) return []
  const base = page.getViewport({ scale: 1 })

  const sorted = [...boxes].sort((a, b) => b.area - a.area)
  const chosen = sorted.slice(0, Math.min(sorted.length, budget.count, MAX_IMAGES_PER_PAGE))
  if (!chosen.length) return []

  const renderScale = Math.min(2.2, 1400 / base.width)
  const viewport = page.getViewport({ scale: renderScale })
  const canvas = document.createElement('canvas')
  canvas.width = Math.max(1, Math.ceil(viewport.width))
  canvas.height = Math.max(1, Math.ceil(viewport.height))
  const context = canvas.getContext('2d', { alpha: false })
  if (!context) return []
  context.fillStyle = '#ffffff'
  context.fillRect(0, 0, canvas.width, canvas.height)
  try {
    await page.render({ canvasContext: context, viewport }).promise
  } catch {
    canvas.width = 0
    canvas.height = 0
    return []
  }

  const out: FoundImage[] = []
  for (const box of chosen) {
    const p0 = viewport.convertToViewportPoint(box.x0, box.y0)
    const p1 = viewport.convertToViewportPoint(box.x1, box.y1)
    const sx = Math.max(0, Math.min(p0[0], p1[0]))
    const sy = Math.max(0, Math.min(p0[1], p1[1]))
    const sw = Math.min(canvas.width - sx, Math.abs(p1[0] - p0[0]))
    const sh = Math.min(canvas.height - sy, Math.abs(p1[1] - p0[1]))
    if (sw < 10 || sh < 10) continue

    const targetWidth = Math.min(MAX_IMAGE_WIDTH, sw)
    const targetHeight = Math.max(1, Math.round(sh * (targetWidth / sw)))
    const crop = document.createElement('canvas')
    crop.width = Math.max(1, Math.round(targetWidth))
    crop.height = targetHeight
    const cropContext = crop.getContext('2d', { alpha: false })
    if (!cropContext) continue
    cropContext.fillStyle = '#ffffff'
    cropContext.fillRect(0, 0, crop.width, crop.height)
    cropContext.drawImage(canvas, sx, sy, sw, sh, 0, 0, crop.width, crop.height)
    const src = crop.toDataURL('image/jpeg', 0.78)
    const width = crop.width
    const height = crop.height
    crop.width = 0
    crop.height = 0

    const bytes = Math.round((src.length * 3) / 4)
    if (bytes > MAX_IMAGE_BYTES) continue // an oversized crop is skipped, not shrunk further
    budget.bytes -= bytes
    budget.count -= 1
    out.push({ box, src, width, height })
    if (budget.count <= 0 || budget.bytes <= 0) break
  }

  canvas.width = 0
  canvas.height = 0
  return out
}

/** Wraps a cropped image as a pseudo-line so it merges into normal reading order. */
function imageLine(page: number, box: ImageBox, src: string, width: number, height: number): Line {
  return {
    text: '',
    x0: box.x0,
    x1: box.x1,
    y: box.y1, // the top edge — lines are ordered top to bottom by descending y
    size: 0,
    page,
    font: '',
    mono: false,
    band: 0,
    image: { src, width, height },
  }
}

/* ------------------------------------------------- running head removal ---- */

const HEADER_ZONE = 0.91
const FOOTER_ZONE = 0.09
const RUNNING_TEXT_MAX_LEN = 150

/**
 * Strips running heads AND footers — publisher lines, chapter/book titles,
 * copyright notices, page numbers — so they don't interrupt the reading flow
 * on every single page. Footers get a lower repeat bar than headers: a page
 * number or copyright line is essentially never a false positive even at two
 * repeats, while a short section heading can legitimately recur, so headers
 * wait for three.
 */
function stripRunningHeads(pages: Line[][], pageHeights: number[]) {
  const headerCounts = new Map<string, Set<number>>()
  const footerCounts = new Map<string, Set<number>>()

  pages.forEach((lines, index) => {
    const height = pageHeights[index] || 792
    for (const line of lines) {
      if (line.image || line.text.length > RUNNING_TEXT_MAX_LEN) continue
      const inHeader = line.y > height * HEADER_ZONE
      const inFooter = line.y < height * FOOTER_ZONE
      if (!inHeader && !inFooter) continue
      const key = normalizeRunningHead(line.text)
      if (!key) continue
      const bucket = inHeader ? headerCounts : footerCounts
      if (!bucket.has(key)) bucket.set(key, new Set())
      bucket.get(key)!.add(index)
    }
  })

  const repeatedHeaders = new Set(
    [...headerCounts.entries()].filter(([, set]) => set.size >= 3).map(([key]) => key),
  )
  const repeatedFooters = new Set(
    [...footerCounts.entries()].filter(([, set]) => set.size >= 2).map(([key]) => key),
  )

  return pages.map((lines, index) => {
    const height = pageHeights[index] || 792
    return lines.filter((line) => {
      if (line.image) return true
      const inHeader = line.y > height * HEADER_ZONE
      const inFooter = line.y < height * FOOTER_ZONE
      if (!inHeader && !inFooter) return true
      if (PAGE_NUMBERISH.test(line.text) && line.text.length <= 20) return false
      const key = normalizeRunningHead(line.text)
      if (inHeader && repeatedHeaders.has(key)) return false
      if (inFooter && repeatedFooters.has(key)) return false
      return true
    })
  })
}

/* -------------------------------------------------------- block builder ---- */

type Draft =
  | { kind: 'text'; lines: Line[]; heading: boolean; bullet: boolean; term: boolean; size: number; page: number }
  | { kind: 'code'; lines: Line[]; page: number }
  | { kind: 'image'; line: Line; page: number }

function buildBlocks(pages: Line[][]): Block[] {
  // Code has its own geometry (a fixed-width font, its own indentation
  // conventions) — mixing it into the body-margin and body-size statistics
  // below would skew them for every other heuristic in this function.
  const flat = pages.flat().filter((l) => !l.image && !l.mono)
  if (!flat.length) return []

  const bodySize = bodySizeOf(flat)
  const bodyLines = flat.filter((l) => Math.abs(l.size - bodySize) < bodySize * 0.12)
  const sample = bodyLines.length > 10 ? bodyLines : flat
  const leftEdge = modeOf(sample.map((l) => l.x0), 2)
  const rightEdge = median(sample.map((l) => l.x1))

  // The font resource key that carries most of the body text — pdf.js only
  // exposes a synthetic id per font, not a real name or weight/style flags,
  // so "this line's font differs from the body's" is the closest available
  // proxy for "this line is emphasised" (bold, italic, a different face).
  const fontWeights = new Map<string, number>()
  for (const line of sample) {
    if (!line.font) continue
    fontWeights.set(line.font, (fontWeights.get(line.font) ?? 0) + line.text.length)
  }
  let bodyFontName = ''
  let bodyFontWeight = -1
  for (const [font, weight] of fontWeights) {
    if (weight > bodyFontWeight) {
      bodyFontName = font
      bodyFontWeight = weight
    }
  }
  const isStyledLine = (line: Line) => Boolean(line.font) && line.font !== bodyFontName

  const gaps: number[] = []
  for (const lines of pages) {
    for (let i = 1; i < lines.length; i++) {
      if (lines[i].image || lines[i - 1].image || lines[i].mono || lines[i - 1].mono) continue
      if (lines[i].band !== lines[i - 1].band) continue
      const gap = lines[i - 1].y - lines[i].y
      if (gap > 0 && gap < bodySize * 4) gaps.push(gap)
    }
  }
  const lineGap = median(gaps) || bodySize * 1.2

  const headingSizes = new Set<number>()
  const isHeading = (line: Line) => {
    const short = line.text.length <= 110
    const closed = /[.!?;,:]$/.test(line.text)
    if (line.size >= bodySize * 1.14 && short) return true
    if (CHAPTERISH.test(line.text) && short && !closed) return true
    // A differently-styled short line only reads as a heading at the outer
    // margin — indented, it's a glossary term instead (isTermStart below),
    // sitting above its own indented definition rather than starting a
    // section.
    if (
      isStyledLine(line) &&
      short &&
      !closed &&
      line.size >= bodySize * 0.98 &&
      line.text.length > 2 &&
      line.x0 <= leftEdge + bodySize * 0.6
    )
      return true
    if (
      short &&
      !closed &&
      line.text.length > 3 &&
      line.text === line.text.toUpperCase() &&
      /[A-Z]{3}/.test(line.text)
    )
      return true
    return false
  }

  // A glossary/definition-list term: short, unclosed, set in a different
  // font from the body text, and indented past the body margin —
  // "Continuous" sitting above its own indented explanation. A section
  // heading sits at the outer margin instead, and ordinary prose isn't
  // short, unpunctuated, indented *and* distinctly styled all at once.
  const isTermStart = (line: Line) => {
    const short = line.text.length <= 45 && line.text.length > 1
    const closed = /[.!?;:,]$/.test(line.text)
    const indented = line.x0 > leftEdge + bodySize * 0.6
    return short && !closed && indented && isStyledLine(line)
  }

  const drafts: Draft[] = []

  for (const lines of pages) {
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i]

      if (line.image) {
        drafts.push({ kind: 'image', line, page: line.page })
        continue
      }

      const previous = i > 0 && !lines[i - 1].image ? lines[i - 1] : null
      const current = drafts[drafts.length - 1]

      // A run of lines set entirely in a monospace font is a code sample —
      // literal line breaks and indentation matter there, so it never joins
      // the ordinary paragraph logic below.
      if (line.mono) {
        if (current?.kind === 'code') current.lines.push(line)
        else drafts.push({ kind: 'code', lines: [line], page: line.page })
        continue
      }

      const heading = isHeading(line)
      const bullet = BULLET.test(line.text)
      const term = !heading && !bullet && isTermStart(line)

      let breaks = !current || current.kind !== 'text'
      if (current && current.kind === 'text') {
        const last = current.lines[current.lines.length - 1]
        if (heading || current.heading || bullet || term) breaks = true
        else if (!previous) {
          // First line after a page or image: keep reading unless it ended short.
          breaks = last.x1 < rightEdge - bodySize * 2.2 && CLOSES.test(last.text)
        } else if (previous.band !== line.band) {
          breaks = previous.x1 < rightEdge - bodySize * 2.2 && CLOSES.test(previous.text)
        } else {
          const gap = previous.y - line.y
          if (gap > lineGap * 1.45) breaks = true
          else if (line.x0 > leftEdge + bodySize * 0.7 && previous.x0 <= leftEdge + bodySize * 0.3)
            breaks = true // a first-line indent
          else if (
            previous.x1 < rightEdge - bodySize * 3 &&
            CLOSES.test(previous.text) &&
            line.x0 <= leftEdge + bodySize * 0.5
          )
            breaks = true // previous paragraph ran short and closed
        }
      }

      if (breaks) drafts.push({ kind: 'text', lines: [line], heading, bullet, term, size: line.size, page: line.page })
      else if (current?.kind === 'text') current.lines.push(line)
      if (heading) headingSizes.add(Math.round(line.size * 2) / 2)
    }
  }

  // Heading levels: the largest size becomes h1, then h2, then h3.
  const ranked = [...headingSizes].sort((a, b) => b - a)
  const levelFor = (size: number): BlockType => {
    const index = ranked.findIndex((s) => Math.abs(s - size) < 0.6)
    if (index <= 0) return 'h1'
    if (index === 1) return 'h2'
    return 'h3'
  }

  const blocks: Block[] = []
  for (const draft of drafts) {
    if (draft.kind === 'image') {
      const img = draft.line.image!
      blocks.push({
        id: `b${blocks.length}`,
        i: blocks.length,
        type: 'image',
        text: '',
        page: draft.page,
        chapter: 0,
        src: img.src,
        width: img.width,
        height: img.height,
      })
      continue
    }

    if (draft.kind === 'code') {
      // Code needs its literal line breaks and indentation kept, not folded
      // into flowing prose — reconstruct each line's leading whitespace from
      // its x-position, since the per-line text was already trimmed.
      const minX0 = Math.min(...draft.lines.map((l) => l.x0))
      const text = draft.lines
        .map((l) => {
          const unit = Math.max(1, l.size * 0.58) // a monospace glyph's rough width
          const spaces = Math.max(0, Math.round((l.x0 - minX0) / unit))
          return ' '.repeat(Math.min(spaces, 40)) + l.text
        })
        .join('\n')
      if (text.trim()) {
        blocks.push({ id: `b${blocks.length}`, i: blocks.length, type: 'code', text, page: draft.page, chapter: 0 })
      }
      continue
    }

    let text = ''
    const links: LinkSpan[] = []
    for (const line of draft.lines) {
      let joinStart: number
      if (!text) {
        text = line.text
        joinStart = 0
      } else if (HYPHEN_END.test(text) && /^[a-z]/.test(line.text)) {
        text = text.slice(0, -1) + line.text
        joinStart = text.length - line.text.length
      } else {
        text += ' ' + line.text
        joinStart = text.length - line.text.length
      }
      if (line.links) {
        for (const span of line.links) links.push({ ...span, start: span.start + joinStart, end: span.end + joinStart })
      }
    }
    text = text.replace(/\s+/g, ' ').trim()
    if (!text) continue

    const mergedLinks = links.length ? mergeLinkSpans(links, text.length) : undefined

    let type: BlockType = 'p'
    let indent: number | undefined
    let strong: { start: number; end: number }[] | undefined

    if (draft.heading) type = levelFor(Math.round(draft.size * 2) / 2)
    else if (draft.bullet) type = 'list'
    else if (draft.term) {
      // A glossary term and its definition: keep it as a paragraph (not a
      // heading, and specifically not a blockquote — its indentation is
      // structural, not a quotation), bold just the term's own lead-in, and
      // carry how deeply it's nested so the reader can show that visually.
      const termLength = Math.min(draft.lines[0].text.length, text.length)
      strong = [{ start: 0, end: termLength }]
      indent = Math.max(1, Math.min(3, Math.round((draft.lines[0].x0 - leftEdge) / (bodySize * 1.3))))
    } else if (draft.size < bodySize * 0.88 && text.length < 220) type = 'caption'
    else if (draft.lines.length > 1 && draft.lines.every((l) => l.x0 > leftEdge + bodySize * 1.2))
      type = 'quote'

    // A "heading" that runs long is almost certainly a misread paragraph.
    if ((type === 'h1' || type === 'h2' || type === 'h3') && text.length > 180) type = 'p'

    blocks.push({
      id: `b${blocks.length}`,
      i: blocks.length,
      type,
      text,
      page: draft.page,
      chapter: 0,
      links: mergedLinks,
      strong,
      indent,
    })
  }
  return blocks
}

/* ------------------------------------------------------------- chapters ---- */

interface OutlineEntry {
  title: string
  level: number
  page: number
}

async function readOutline(pdf: pdfjs.PDFDocumentProxy): Promise<OutlineEntry[]> {
  type Outline = Awaited<ReturnType<typeof pdf.getOutline>>
  let outline: Outline | null = null
  try {
    outline = await pdf.getOutline()
  } catch {
    return []
  }
  if (!outline?.length) return []

  const entries: OutlineEntry[] = []
  const walk = async (nodes: NonNullable<Outline>, level: number) => {
    for (const node of nodes) {
      let page = 0
      try {
        const dest = typeof node.dest === 'string' ? await pdf.getDestination(node.dest) : node.dest
        const ref = Array.isArray(dest) ? dest[0] : null
        if (ref && typeof ref === 'object') page = (await pdf.getPageIndex(ref as never)) + 1
      } catch {
        /* one broken destination should not cost us the whole outline */
      }
      const title = (node.title || '').replace(/\s+/g, ' ').trim()
      if (title && page > 0) entries.push({ title, level, page })
      if (node.items?.length && level < 1) await walk(node.items, level + 1)
    }
  }
  await walk(outline, 0)
  return entries
}

function chaptersFrom(blocks: Block[], outline: OutlineEntry[], title: string): Chapter[] {
  const chapters: Chapter[] = []

  if (outline.length >= 2 && blocks.length) {
    const used = new Set<number>()
    for (const entry of outline) {
      const key = entry.title.toLowerCase().slice(0, 24)
      const candidates = blocks.filter((b) => b.page === entry.page && !used.has(b.i))
      const match =
        candidates.find((b) => b.text.toLowerCase().startsWith(key)) ??
        candidates.find((b) => b.type !== 'p' && b.type !== 'list' && b.type !== 'image') ??
        candidates[0] ??
        blocks.find((b) => b.page >= entry.page)
      if (!match || chapters.some((c) => c.blockIndex === match.i)) continue
      used.add(match.i)
      chapters.push({
        id: `c${chapters.length}`,
        title: entry.title,
        blockIndex: match.i,
        page: match.page,
        level: entry.level,
      })
    }
  }

  if (chapters.length < 2) {
    chapters.length = 0
    const h1 = blocks.filter((b) => b.type === 'h1')
    const source = h1.length >= 2 ? h1 : blocks.filter((b) => b.type === 'h1' || b.type === 'h2')
    for (const block of source.slice(0, 500)) {
      chapters.push({
        id: `c${chapters.length}`,
        title: block.text.slice(0, 120),
        blockIndex: block.i,
        page: block.page,
        level: block.type === 'h1' ? 0 : 1,
      })
    }
  }

  chapters.sort((a, b) => a.blockIndex - b.blockIndex)
  if (!chapters.length || chapters[0].blockIndex > 0) {
    chapters.unshift({
      id: 'start',
      title: title || 'Beginning',
      blockIndex: 0,
      page: 1,
      level: 0,
    })
  }
  chapters.forEach((chapter, index) => {
    chapter.id = `c${index}`
  })

  // Stamp every block with the chapter it belongs to.
  let cursor = 0
  for (const block of blocks) {
    while (cursor + 1 < chapters.length && chapters[cursor + 1].blockIndex <= block.i) cursor++
    block.chapter = cursor
  }
  return chapters
}

/* --------------------------------------------------------------- public ---- */

const toBytes = (data: ArrayBuffer | Uint8Array) =>
  data instanceof Uint8Array ? new Uint8Array(data) : new Uint8Array(data.slice(0))

async function renderFromDoc(
  pdf: pdfjs.PDFDocumentProxy,
  pageNumber: number,
  targetWidth: number,
  quality: number,
) {
  const page = await pdf.getPage(Math.min(Math.max(1, pageNumber), pdf.numPages))
  const base = page.getViewport({ scale: 1 })
  const viewport = page.getViewport({ scale: Math.min(4, targetWidth / base.width) })
  const canvas = document.createElement('canvas')
  canvas.width = Math.round(viewport.width)
  canvas.height = Math.round(viewport.height)
  const context = canvas.getContext('2d', { alpha: false })
  if (!context) return undefined
  context.fillStyle = '#ffffff'
  context.fillRect(0, 0, canvas.width, canvas.height)
  await page.render({ canvasContext: context, viewport }).promise
  const url = canvas.toDataURL('image/jpeg', quality)
  canvas.width = 0
  canvas.height = 0
  page.cleanup()
  return url
}

/** Total image budget for one book — bounded so an illustrated book stays local-friendly. */
const MAX_IMAGES_PER_BOOK = 140
const MAX_IMAGE_BYTES_PER_BOOK = 26 * 1024 * 1024

export async function extractBook(
  data: ArrayBuffer,
  fallbackTitle: string,
  onProgress?: (p: ExtractProgress) => void,
): Promise<ExtractResult> {
  onProgress?.({ phase: 'opening', done: 0, total: 1 })
  const pdf = await pdfjs.getDocument({ data: toBytes(data), isEvalSupported: false }).promise

  try {
    let title = fallbackTitle
    let author = ''
    try {
      const meta = await pdf.getMetadata()
      const info = meta.info as { Title?: string; Author?: string } | undefined
      if (info?.Title && info.Title.trim().length > 2 && !/^untitled/i.test(info.Title))
        title = info.Title.trim()
      if (info?.Author) author = info.Author.trim()
    } catch {
      /* metadata is a nicety, not a requirement */
    }

    const pages: Line[][] = []
    const heights: number[] = []
    const imageBudget = { count: MAX_IMAGES_PER_BOOK, bytes: MAX_IMAGE_BYTES_PER_BOOK }

    for (let n = 1; n <= pdf.numPages; n++) {
      const page = await pdf.getPage(n)
      const viewport = page.getViewport({ scale: 1 })
      heights.push(viewport.height)

      const [content, pageLinks, rawBoxes] = await Promise.all([
        page.getTextContent(),
        readPageLinks(pdf, page),
        findImageBoxes(page, viewport.width, viewport.height),
      ])
      // pdf.js mixes marked-content markers into the item list; only the
      // entries carrying a `str` are actual glyph runs.
      const items = content.items.filter(
        (item) => typeof (item as { str?: unknown }).str === 'string',
      ) as unknown as RawItem[]
      const lines = itemsToLines(items, n, viewport.width, pageLinks, content.styles as PageStyles)
      const imageBoxes = dedupeImageBoxes(rawBoxes)

      let pageLines = lines
      let flattened = false

      if (
        imageBoxes.length &&
        imageBudget.count > 0 &&
        assessGraphicPage(lines, imageBoxes, viewport.width, viewport.height)
      ) {
        // This page's design can't be reflowed without losing its meaning —
        // a cover, a divider, a diagram with labels baked into the layout.
        // Keep it exactly as it looked, as one picture, rather than shredding
        // it into stray headline text and overlapping image fragments.
        try {
          const whole = await renderWholePage(page, 1200, 0.8)
          const bytes = whole ? Math.round((whole.src.length * 3) / 4) : Infinity
          if (whole && bytes <= MAX_WHOLE_PAGE_BYTES) {
            imageBudget.count -= 1
            imageBudget.bytes -= bytes
            pageLines = [
              imageLine(
                n,
                { x0: 0, y0: 0, x1: viewport.width, y1: viewport.height, area: viewport.width * viewport.height },
                whole.src,
                whole.width,
                whole.height,
              ),
            ]
            flattened = true
          }
        } catch {
          /* fall through to the normal per-image extraction below */
        }
      }

      if (!flattened && imageBoxes.length && imageBudget.count > 0) {
        try {
          const found = await extractPageImages(page, imageBoxes, imageBudget)
          if (found.length) {
            for (const image of found) pageLines.push(imageLine(n, image.box, image.src, image.width, image.height))
            pageLines.sort(compareLines)
          }
        } catch {
          /* a page whose images fail to extract still keeps its text */
        }
      }

      pages.push(pageLines)
      page.cleanup()
      if (n % 4 === 0 || n === pdf.numPages) {
        onProgress?.({ phase: 'reading', done: n, total: pdf.numPages })
        await yieldToPaint()
      }
    }

    onProgress?.({ phase: 'shaping', done: 0, total: 1 })
    await yieldToPaint()

    const cleaned = stripRunningHeads(pages, heights)
    const blocks = buildBlocks(cleaned)
    const wordCount = blocks.reduce((sum, b) => sum + (b.text ? b.text.split(/\s+/).length : 0), 0)
    const scanned = wordCount < Math.max(40, pdf.numPages * 12)

    const outline = await readOutline(pdf)
    const chapters = chaptersFrom(blocks, outline, title)

    onProgress?.({ phase: 'cover', done: 0, total: 1 })
    let cover: string | undefined
    try {
      cover = await renderFromDoc(pdf, 1, 420, 0.72)
    } catch {
      /* a missing cover is only cosmetic */
    }

    onProgress?.({ phase: 'done', done: 1, total: 1 })
    return { blocks, chapters, pageCount: pdf.numPages, wordCount, title, author, cover, scanned }
  } finally {
    void pdf.destroy()
  }
}

/** Used by the page-image fallback for PDFs that carry no text layer. */
export async function openDocument(data: ArrayBuffer) {
  return pdfjs.getDocument({ data: toBytes(data), isEvalSupported: false }).promise
}

export async function renderPage(
  pdf: pdfjs.PDFDocumentProxy,
  pageNumber: number,
  canvas: HTMLCanvasElement,
  cssWidth: number,
) {
  const page = await pdf.getPage(pageNumber)
  const base = page.getViewport({ scale: 1 })
  const dpr = Math.min(3, window.devicePixelRatio || 1)
  const viewport = page.getViewport({ scale: (cssWidth / base.width) * dpr })
  canvas.width = Math.round(viewport.width)
  canvas.height = Math.round(viewport.height)
  canvas.style.width = `${cssWidth}px`
  canvas.style.height = `${Math.round(viewport.height / dpr)}px`
  const context = canvas.getContext('2d', { alpha: false })
  if (!context) return
  context.fillStyle = '#ffffff'
  context.fillRect(0, 0, canvas.width, canvas.height)
  await page.render({ canvasContext: context, viewport }).promise
  page.cleanup()
}

export type PdfDoc = pdfjs.PDFDocumentProxy

// TEMP DEBUG — remove before shipping.
export const __debug = { itemsToLines, buildBlocks, bodySizeOf, median }
