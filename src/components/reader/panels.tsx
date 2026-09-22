import { useEffect, useMemo, useRef, useState } from 'react'
import { Icon } from '../Icon'
import { Range as RangeControl, Segmented, Sheet, Switch } from '../ui'
import { FONTS, useSettings } from '../../state/settings'
import { formatRelative } from '../../lib/util'
import type { Annotation, Block, Chapter, HighlightColor } from '../../lib/types'

export const HIGHLIGHT_COLORS: HighlightColor[] = ['butter', 'rose', 'sage', 'sky', 'lilac']

/* ------------------------------------------------------------ type menu -- */

export function TunePanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { settings, set, reset } = useSettings()

  return (
    <Sheet
      open={open}
      onClose={onClose}
      variant="side"
      title="Reading"
      headExtra={
        <button type="button" className="btn btn--ghost btn--sm" onClick={reset}>
          Reset
        </button>
      }
    >
      <div className="sheet__body tune">
        <div className="tune__group">
          <span className="tune__label">Theme</span>
          <div className="theme-row">
            {(['light', 'sepia', 'dark'] as const).map((theme) => (
              <button
                key={theme}
                type="button"
                className="theme-swatch"
                aria-pressed={settings.theme === theme}
                onClick={() => set('theme', theme)}
              >
                <span className={`theme-swatch__chip theme-swatch__chip--${theme}`}>Aa</span>
                {theme[0].toUpperCase() + theme.slice(1)}
              </button>
            ))}
          </div>
          <Switch
            checked={settings.theme === 'system'}
            onChange={(on) => set('theme', on ? 'system' : 'light')}
            label="Follow the system"
            hint="Light by day, dark at night."
          />
        </div>

        <div className="tune__group">
          <span className="tune__label">Typeface</span>
          <div className="font-row">
            {FONTS.map((font) => (
              <button
                key={font.id}
                type="button"
                className="font-option"
                aria-pressed={settings.font === font.id}
                onClick={() => set('font', font.id)}
              >
                <span className="font-option__name" style={{ fontFamily: font.stack }}>
                  {font.name}
                </span>
                <span className="font-option__note">{font.note}</span>
              </button>
            ))}
          </div>
        </div>

        <RangeControl
          label="Text size"
          value={settings.fontSize}
          min={14}
          max={30}
          onChange={(value) => set('fontSize', value)}
          format={(value) => `${value}px`}
        />
        <RangeControl
          label="Line spacing"
          value={settings.lineHeight}
          min={1.25}
          max={2.2}
          step={0.02}
          onChange={(value) => set('lineHeight', value)}
          format={(value) => value.toFixed(2)}
        />
        <RangeControl
          label="Line width"
          value={settings.measure}
          min={40}
          max={100}
          onChange={(value) => set('measure', value)}
          format={(value) => `${value} chars`}
        />
        <RangeControl
          label="Side margins"
          value={settings.margin}
          min={8}
          max={80}
          onChange={(value) => set('margin', value)}
          format={(value) => `${value}px`}
        />
        <RangeControl
          label="Paragraph spacing"
          value={settings.paragraphSpacing}
          min={0}
          max={2}
          step={0.05}
          onChange={(value) => set('paragraphSpacing', value)}
          format={(value) => `${value.toFixed(2)}em`}
        />

        <div className="tune__group">
          <span className="tune__label">Layout</span>
          <Segmented
            ariaLabel="Reading layout"
            value={settings.mode}
            onChange={(value) => set('mode', value)}
            options={[
              { value: 'scroll', label: 'Scroll' },
              { value: 'page', label: 'Pages' },
            ]}
          />
          <Switch
            checked={settings.justify}
            onChange={(on) => set('justify', on)}
            label="Justify text"
            hint="Even right edge, with hyphenation."
          />
        </div>
      </div>
    </Sheet>
  )
}

/* ------------------------------------------------------------- contents -- */

type Tab = 'contents' | 'notes' | 'search'

interface ContentsPanelProps {
  open: boolean
  onClose: () => void
  tab: Tab
  onTab: (tab: Tab) => void
  chapters: Chapter[]
  blocks: Block[]
  currentChapter: number
  annotations: Annotation[]
  onJump: (blockIndex: number, mark?: { start: number; end: number }) => void
  onEditNote: (annotation: Annotation) => void
  onDeleteAnnotation: (id: string) => void
}

export function ContentsPanel({
  open,
  onClose,
  tab,
  onTab,
  chapters,
  blocks,
  currentChapter,
  annotations,
  onJump,
  onEditNote,
  onDeleteAnnotation,
}: ContentsPanelProps) {
  const [query, setQuery] = useState('')
  const searchRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (open && tab === 'search') searchRef.current?.focus()
  }, [open, tab])

  const hits = useMemo(() => {
    const needle = query.trim().toLowerCase()
    if (needle.length < 2) return []
    const found: { blockIndex: number; start: number; text: string; chapter: number }[] = []
    for (const block of blocks) {
      const haystack = block.text.toLowerCase()
      let from = 0
      while (found.length < 400) {
        const at = haystack.indexOf(needle, from)
        if (at === -1) break
        found.push({ blockIndex: block.i, start: at, text: block.text, chapter: block.chapter })
        from = at + needle.length
      }
      if (found.length >= 400) break
    }
    return found
  }, [blocks, query])

  const bookmarks = annotations.filter((a) => a.kind === 'bookmark')
  const marks = annotations.filter((a) => a.kind !== 'bookmark')

  return (
    <Sheet open={open} onClose={onClose} variant="side" title="Contents">
      <div className="panel__tabs" role="tablist">
        {(
          [
            ['contents', 'Chapters'],
            ['notes', 'Notes'],
            ['search', 'Search'],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            role="tab"
            className="panel__tab"
            aria-selected={tab === id}
            onClick={() => onTab(id)}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === 'contents' && (
        <div className="panel__list">
          {chapters.map((chapter, index) => (
            <button
              key={chapter.id}
              type="button"
              className={`toc__item${chapter.level > 0 ? ' toc__item--sub' : ''}${
                index === currentChapter ? ' is-current' : ''
              }`}
              onClick={() => {
                onJump(chapter.blockIndex)
                onClose()
              }}
            >
              <span>{chapter.title}</span>
              <span className="toc__page">p{chapter.page}</span>
            </button>
          ))}
          {chapters.length <= 1 && (
            <p className="panel__empty">
              This PDF has no table of contents, and no headings were detected — so the whole book is
              one long chapter.
            </p>
          )}
        </div>
      )}

      {tab === 'notes' && (
        <div className="panel__list">
          {bookmarks.length > 0 && (
            <>
              <p className="rail__title" style={{ padding: '4px 4px 6px' }}>
                Bookmarks
              </p>
              {bookmarks.map((mark) => (
                <button
                  key={mark.id}
                  type="button"
                  className="toc__item"
                  onClick={() => {
                    onJump(mark.blockIndex)
                    onClose()
                  }}
                >
                  <Icon name="bookmark" size={15} />
                  <span
                    style={{
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {mark.text.slice(0, 70) || 'Bookmark'}
                  </span>
                </button>
              ))}
            </>
          )}

          {marks.length > 0 && (
            <p className="rail__title" style={{ padding: '10px 4px 6px' }}>
              Highlights &amp; notes
            </p>
          )}
          {marks.map((mark) => (
            <div className="note-card" key={mark.id}>
              <button
                type="button"
                style={{ display: 'block', width: '100%', textAlign: 'left' }}
                onClick={() => {
                  onJump(mark.blockIndex)
                  onClose()
                }}
              >
                <span
                  className="note-card__quote"
                  style={{
                    borderColor: `var(--swatch-${mark.color}, var(--accent))`,
                    display: 'block',
                  }}
                >
                  {mark.text}
                </span>
                {mark.note && <span className="note-card__note">{mark.note}</span>}
              </button>
              <div className="note-card__foot">
                <span>{formatRelative(mark.createdAt)}</span>
                <button
                  type="button"
                  className="btn btn--ghost btn--sm"
                  style={{ marginLeft: 'auto' }}
                  onClick={() => onEditNote(mark)}
                >
                  <Icon name="note" size={14} />
                  {mark.note ? 'Edit note' : 'Add note'}
                </button>
                <button
                  type="button"
                  className="icon-btn"
                  style={{ width: 28, height: 28 }}
                  aria-label="Delete highlight"
                  onClick={() => onDeleteAnnotation(mark.id)}
                >
                  <Icon name="trash" size={14} />
                </button>
              </div>
            </div>
          ))}

          {!annotations.length && (
            <p className="panel__empty">
              Select any passage to highlight it, add a note, or drop a bookmark. They all show up
              here.
            </p>
          )}
        </div>
      )}

      {tab === 'search' && (
        <>
          <div className="panel__search">
            <input
              ref={searchRef}
              className="input"
              type="search"
              value={query}
              placeholder="Search inside this book"
              onChange={(event) => setQuery(event.target.value)}
            />
          </div>
          <div className="panel__list">
            {query.trim().length >= 2 && !hits.length && (
              <p className="panel__empty">No matches for “{query}”.</p>
            )}
            {hits.map((hit, index) => (
              <button
                key={`${hit.blockIndex}-${hit.start}-${index}`}
                type="button"
                className="hit"
                onClick={() => {
                  onJump(hit.blockIndex, {
                    start: hit.start,
                    end: hit.start + query.trim().length,
                  })
                  onClose()
                }}
              >
                <span>
                  {hit.text.slice(Math.max(0, hit.start - 44), hit.start)}
                  <mark>{hit.text.slice(hit.start, hit.start + query.trim().length)}</mark>
                  {hit.text.slice(hit.start + query.trim().length, hit.start + query.trim().length + 60)}
                </span>
                <span className="hit__where">
                  {chapters[hit.chapter]?.title ?? 'Chapter'} · page {blocks[hit.blockIndex]?.page}
                </span>
              </button>
            ))}
            {query.trim().length < 2 && (
              <p className="panel__empty">Type at least two characters to search.</p>
            )}
          </div>
        </>
      )}
    </Sheet>
  )
}

/* ----------------------------------------------------------- note sheet -- */

export function NoteEditor({
  annotation,
  onClose,
  onSave,
  onDelete,
}: {
  annotation: Annotation | null
  onClose: () => void
  onSave: (note: string, color: HighlightColor) => void
  onDelete: () => void
}) {
  const [note, setNote] = useState('')
  const [color, setColor] = useState<HighlightColor>('butter')

  useEffect(() => {
    setNote(annotation?.note ?? '')
    setColor(annotation?.color ?? 'butter')
  }, [annotation])

  return (
    <Sheet
      open={Boolean(annotation)}
      onClose={onClose}
      title={annotation?.note ? 'Edit note' : 'Add a note'}
      footer={
        <>
          <button type="button" className="btn btn--danger" onClick={onDelete} style={{ marginRight: 'auto' }}>
            <Icon name="trash" size={15} />
            Delete
          </button>
          <button type="button" className="btn btn--ghost" onClick={onClose}>
            Cancel
          </button>
          <button type="button" className="btn btn--primary" onClick={() => onSave(note, color)}>
            Save
          </button>
        </>
      }
    >
      <div className="sheet__body note-editor">
        <div className="note-editor__quote">{annotation?.text}</div>
        <div className="swatch-row">
          {HIGHLIGHT_COLORS.map((option) => (
            <button
              key={option}
              type="button"
              className={`swatch swatch--${option}`}
              aria-label={option}
              aria-pressed={color === option}
              onClick={() => setColor(option)}
            />
          ))}
        </div>
        <textarea
          className="input"
          value={note}
          placeholder="What did you want to remember about this?"
          onChange={(event) => setNote(event.target.value)}
        />
      </div>
    </Sheet>
  )
}

/* -------------------------------------------------------- selection pop -- */

export interface SelectionState {
  x: number
  y: number
  /** One piece per block the selection touches. */
  pieces: { blockIndex: number; start: number; end: number; text: string }[]
  text: string
  /** Set when the selection landed on an existing highlight. */
  annotationId?: string
}

export function SelectionMenu({
  selection,
  onHighlight,
  onNote,
  onCopy,
  onListen,
  onRemove,
}: {
  selection: SelectionState
  onHighlight: (color: HighlightColor) => void
  onNote: () => void
  onCopy: () => void
  onListen: () => void
  onRemove: () => void
}) {
  return (
    <div
      className="selection-menu"
      style={{ left: selection.x, top: selection.y, transform: 'translate(-50%, -100%)' }}
      role="toolbar"
      aria-label="Selection actions"
    >
      {HIGHLIGHT_COLORS.map((color) => (
        <button
          key={color}
          type="button"
          className={`swatch swatch--${color}`}
          aria-label={`Highlight ${color}`}
          onClick={() => onHighlight(color)}
        />
      ))}
      <span className="selection-menu__sep" />
      <button type="button" className="icon-btn" aria-label="Add note" onClick={onNote}>
        <Icon name="note" size={17} />
      </button>
      <button type="button" className="icon-btn" aria-label="Copy" onClick={onCopy}>
        <Icon name="edit" size={17} />
      </button>
      <button type="button" className="icon-btn" aria-label="Listen from here" onClick={onListen}>
        <Icon name="headphones" size={17} />
      </button>
      {selection.annotationId && (
        <button type="button" className="icon-btn" aria-label="Remove highlight" onClick={onRemove}>
          <Icon name="trash" size={17} />
        </button>
      )}
    </div>
  )
}
