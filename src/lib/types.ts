/** Shared data model. Everything here lives locally first; sync is additive. */

export type ID = string

export interface Folder {
  id: ID
  name: string
  /** Accent hue (0-360) used for the folder chip. */
  hue: number
  order: number
  createdAt: number
  updatedAt: number
  deleted?: boolean
}

export interface Book {
  id: ID
  title: string
  author: string
  folderId: ID | null
  fileName: string
  fileSize: number
  pageCount: number
  wordCount: number
  /** Minutes, at ~230 wpm. */
  minutes: number
  /** Small JPEG data URL rendered from page one. */
  cover?: string
  /** True when the PDF carries no extractable text layer (a scan). */
  scanned?: boolean
  addedAt: number
  lastOpenedAt?: number
  updatedAt: number
  deleted?: boolean
}

export type BlockType = 'h1' | 'h2' | 'h3' | 'p' | 'quote' | 'list' | 'caption' | 'image' | 'code' | 'table'

/** A clickable run inside a block's text: an external URL or a jump to a page. */
export interface LinkSpan {
  start: number
  end: number
  /** Set for a link to an external URL. */
  href?: string
  /** Set for a link to elsewhere in the PDF (1-based page number). */
  page?: number
}

export interface Block {
  id: string
  /** Position in the reading order. */
  i: number
  type: BlockType
  text: string
  /** 1-based source page this block began on. */
  page: number
  /** Index into `BookDoc.chapters`. */
  chapter: number
  /** Clickable spans inside `text` — external links and internal page jumps. */
  links?: LinkSpan[]
  /** Runs of `text` that should render bold — a glossary term's lead-in. */
  strong?: { start: number; end: number }[]
  /** 0-3: how deeply this reads as nested (a definition's body, a sub-list) —
   *  rendered as a scaled left margin rather than losing the structure. */
  indent?: number
  /** `type: 'image'` only: the picture itself, as a JPEG data URL. */
  src?: string
  /** `type: 'image'` only: natural size, for an aspect-ratio placeholder. */
  width?: number
  height?: number
  /** `type: 'table'` only: one array of cell strings per row. */
  rows?: string[][]
  /** `type: 'table'` only: whether `rows[0]` is a header row. */
  tableHeader?: boolean
}

export interface Chapter {
  id: string
  title: string
  /** Index of the first block of the chapter. */
  blockIndex: number
  page: number
  level: number
}

/** The reflowed text of a book. Large, so it is kept out of the book record. */
export interface BookDoc {
  bookId: ID
  version: number
  blocks: Block[]
  chapters: Chapter[]
}

export interface BookFile {
  bookId: ID
  blob: Blob
}

export interface Progress {
  bookId: ID
  /** Index of the top-most visible block. */
  blockIndex: number
  /** 0-1 through the book. */
  percent: number
  /** Furthest point ever reached, 0-1. */
  furthest: number
  updatedAt: number
}

export type AnnotationKind = 'highlight' | 'note' | 'bookmark'

export type HighlightColor = 'butter' | 'rose' | 'sage' | 'sky' | 'lilac'

export interface Annotation {
  id: ID
  bookId: ID
  kind: AnnotationKind
  blockId: string
  blockIndex: number
  /** Character offsets inside the block's text. Equal for bookmarks. */
  start: number
  end: number
  /** The highlighted text, kept so lists read well without loading the doc. */
  text: string
  note?: string
  color: HighlightColor
  createdAt: number
  updatedAt: number
  deleted?: boolean
}

export type ThemeName = 'light' | 'sepia' | 'dark' | 'system'
export type ReadingFont = 'literata' | 'lora' | 'fraunces' | 'inter' | 'hyperlegible'
export type ReadingMode = 'scroll' | 'page'
export type Ambience = 'none' | 'rain' | 'fireplace' | 'cafe' | 'forest'

export interface Settings {
  theme: ThemeName
  font: ReadingFont
  fontSize: number
  lineHeight: number
  /** Content column width in characters. */
  measure: number
  margin: number
  paragraphSpacing: number
  justify: boolean
  mode: ReadingMode
  /** Voice URI chosen for Listen Mode. */
  voiceURI: string | null
  rate: number
  pitch: number
  ttsVolume: number
  ambience: Ambience
  ambienceVolume: number
  highlightColor: HighlightColor
  /** Keep the screen awake while listening. */
  keepAwake: boolean
  reduceMotion: boolean
}

export interface User {
  id: ID
  email: string
  name: string
  createdAt: number
}

/** Anything that syncs is one of these; the server stores them verbatim. */
export interface SyncPayload {
  folders: Folder[]
  books: Omit<Book, 'cover'>[]
  annotations: Annotation[]
  progress: Progress[]
}
