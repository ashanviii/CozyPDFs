import { useEffect, useMemo, useRef, useState } from 'react'
import { TopBar } from '../components/TopBar'
import { Icon } from '../components/Icon'
import { Confirm, Menu, Sheet, useMenu } from '../components/ui'
import { describePhase, useLibrary } from '../state/library'
import { useToast } from '../state/toast'
import { navigate } from '../lib/router'
import { formatDuration, hueFrom, plural } from '../lib/util'
import type { Book } from '../lib/types'

const UNSORTED = '__unsorted__'

export function LibraryView({ folderId }: { folderId: string | null }) {
  const library = useLibrary()
  const toast = useToast()
  const [query, setQuery] = useState('')
  const [dragging, setDragging] = useState(false)
  const [menuBook, setMenuBook] = useState<Book | null>(null)
  const [editing, setEditing] = useState<Book | null>(null)
  const [moving, setMoving] = useState<Book | null>(null)
  const [deleting, setDeleting] = useState<Book | null>(null)
  const [newFolder, setNewFolder] = useState(false)
  const [dropFolder, setDropFolder] = useState<string | null>(null)
  const [folderMenu, setFolderMenu] = useState<{ id: string; x: number; y: number } | null>(null)
  const [renamingFolder, setRenamingFolder] = useState<string | null>(null)
  const [deletingFolder, setDeletingFolder] = useState<string | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)
  const menu = useMenu()

  const { books, folders, progress, local, loading, imports } = library

  /* ----------------------------------------------------------- filters -- */

  const counts = useMemo(() => {
    const map = new Map<string, number>()
    let unsorted = 0
    for (const book of books) {
      if (book.folderId) map.set(book.folderId, (map.get(book.folderId) ?? 0) + 1)
      else unsorted++
    }
    return { map, unsorted }
  }, [books])

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase()
    return books.filter((book) => {
      if (folderId === UNSORTED && book.folderId) return false
      if (folderId && folderId !== UNSORTED && book.folderId !== folderId) return false
      if (!needle) return true
      return (
        book.title.toLowerCase().includes(needle) ||
        book.author.toLowerCase().includes(needle) ||
        book.fileName.toLowerCase().includes(needle)
      )
    })
  }, [books, folderId, query])

  const continueBook = useMemo(() => {
    if (folderId || query) return null
    const candidate = books.find((book) => {
      const p = progress[book.id]
      return book.lastOpenedAt && p && p.percent > 0.005 && p.percent < 0.995 && local.has(book.id)
    })
    return candidate ?? null
  }, [books, folderId, local, progress, query])

  const currentFolder = folders.find((folder) => folder.id === folderId)
  const heading =
    folderId === UNSORTED ? 'Unsorted' : currentFolder ? currentFolder.name : 'Your library'
  // The true first-open state — nothing added yet anywhere, not just this
  // folder or search — gets the simple "drop a PDF and start reading"
  // framing; an empty folder or search still gets the ordinary empty state.
  const isFirstRun = !folderId && !query && books.length === 0

  /* ------------------------------------------------------------- drops -- */

  useEffect(() => {
    let depth = 0
    const hasFiles = (event: DragEvent) =>
      Array.from(event.dataTransfer?.types ?? []).includes('Files')

    const onEnter = (event: DragEvent) => {
      if (!hasFiles(event)) return
      depth++
      setDragging(true)
    }
    const onOver = (event: DragEvent) => {
      if (hasFiles(event)) event.preventDefault()
    }
    const onLeave = (event: DragEvent) => {
      if (!hasFiles(event)) return
      depth = Math.max(0, depth - 1)
      if (depth === 0) setDragging(false)
    }
    const onDrop = (event: DragEvent) => {
      if (!hasFiles(event)) return
      event.preventDefault()
      depth = 0
      setDragging(false)
      const files = Array.from(event.dataTransfer?.files ?? [])
      if (files.length) void library.addFiles(files)
    }

    window.addEventListener('dragenter', onEnter)
    window.addEventListener('dragover', onOver)
    window.addEventListener('dragleave', onLeave)
    window.addEventListener('drop', onDrop)
    return () => {
      window.removeEventListener('dragenter', onEnter)
      window.removeEventListener('dragover', onOver)
      window.removeEventListener('dragleave', onLeave)
      window.removeEventListener('drop', onDrop)
    }
  }, [library])

  const pickFiles = () => fileInput.current?.click()

  const open = (book: Book) => {
    if (!local.has(book.id)) {
      toast(`"${book.title}" is in your library but its file is on another device.`, 'warn')
      return
    }
    navigate({ name: 'reader', bookId: book.id })
  }

  return (
    <div className="shell">
      <TopBar query={query} onQuery={setQuery} onAdd={pickFiles} />

      <input
        ref={fileInput}
        type="file"
        accept="application/pdf,.pdf"
        multiple
        hidden
        onChange={(event) => {
          const files = Array.from(event.target.files ?? [])
          if (files.length) void library.addFiles(files)
          event.target.value = ''
        }}
      />

      <div className="main">
        <nav className="rail" aria-label="Folders">
          <p className="rail__title">Library</p>
          <RailItem
            active={!folderId}
            label="All books"
            icon="book"
            count={books.length}
            onClick={() => navigate({ name: 'library', folderId: null })}
          />
          <RailItem
            active={folderId === UNSORTED}
            label="Unsorted"
            icon="inbox"
            count={counts.unsorted}
            onClick={() => navigate({ name: 'library', folderId: UNSORTED })}
            onDropBook={(bookId) => void library.moveBook(bookId, null)}
            isDropTarget={dropFolder === UNSORTED}
            setDropTarget={(on) => setDropFolder(on ? UNSORTED : null)}
          />

          <p className="rail__title">Folders</p>
          {folders.map((folder) => (
            <RailItem
              key={folder.id}
              active={folderId === folder.id}
              label={folder.name}
              hue={folder.hue}
              count={counts.map.get(folder.id) ?? 0}
              onClick={() => navigate({ name: 'library', folderId: folder.id })}
              onDropBook={(bookId) => void library.moveBook(bookId, folder.id)}
              isDropTarget={dropFolder === folder.id}
              setDropTarget={(on) => setDropFolder(on ? folder.id : null)}
              onContext={(event) => {
                event.preventDefault()
                setFolderMenu({ id: folder.id, x: event.clientX, y: event.clientY })
              }}
            />
          ))}
          {!folders.length && (
            <p className="rail__item" style={{ color: 'var(--ink-faint)', fontSize: 13 }}>
              None yet
            </p>
          )}
          <button type="button" className="rail__item" onClick={() => setNewFolder(true)}>
            <Icon name="folderPlus" size={16} />
            New folder
          </button>
        </nav>

        <div className="shelf">
          <div className="chips">
            <button
              type="button"
              className={`chip${!folderId ? ' is-active' : ''}`}
              onClick={() => navigate({ name: 'library', folderId: null })}
            >
              All books
            </button>
            <button
              type="button"
              className={`chip${folderId === UNSORTED ? ' is-active' : ''}`}
              onClick={() => navigate({ name: 'library', folderId: UNSORTED })}
            >
              Unsorted
            </button>
            {folders.map((folder) => (
              <button
                key={folder.id}
                type="button"
                className={`chip${folderId === folder.id ? ' is-active' : ''}`}
                onClick={() => navigate({ name: 'library', folderId: folder.id })}
              >
                <span className="folder-dot" style={{ '--hue': folder.hue } as never} />
                {folder.name}
              </button>
            ))}
            <button type="button" className="chip" onClick={() => setNewFolder(true)}>
              <Icon name="plus" size={14} />
              Folder
            </button>
          </div>

          <div className="shelf__head">
            <div>
              <h1 className="shelf__title">{heading}</h1>
              <p className="shelf__sub">
                {loading
                  ? 'Opening your shelf…'
                  : query
                    ? `${plural(visible.length, 'match', 'matches')} for “${query}”`
                    : plural(visible.length, 'book')}
              </p>
            </div>
            {currentFolder && (
              <div className="shelf__actions">
                <button
                  type="button"
                  className="btn btn--ghost btn--sm"
                  onClick={() => setRenamingFolder(currentFolder.id)}
                >
                  <Icon name="edit" size={15} />
                  Rename
                </button>
                <button
                  type="button"
                  className="btn btn--ghost btn--sm btn--danger"
                  onClick={() => setDeletingFolder(currentFolder.id)}
                >
                  <Icon name="trash" size={15} />
                  Delete folder
                </button>
              </div>
            )}
          </div>

          {imports.length > 0 && (
            <div className="imports">
              {imports.map((job) => (
                <div className="import" key={job.id}>
                  {job.phase === 'failed' ? (
                    <Icon name="alert" size={18} />
                  ) : job.phase === 'done' ? (
                    <Icon name="check" size={18} />
                  ) : (
                    <span className="spinner" />
                  )}
                  <div className="import__meta">
                    <div className="import__name">{job.name}</div>
                    <div className="import__phase">
                      {job.error ?? describePhase(job)}
                      {job.phase === 'reading' ? ` · page ${job.done} of ${job.total}` : ''}
                    </div>
                    <div className="import__track">
                      <i
                        style={{
                          width:
                            job.phase === 'reading'
                              ? `${Math.round((job.done / Math.max(1, job.total)) * 100)}%`
                              : job.phase === 'done'
                                ? '100%'
                                : job.phase === 'queued'
                                  ? '4%'
                                  : '92%',
                        }}
                      />
                    </div>
                  </div>
                  {(job.phase === 'failed' || job.phase === 'done') && (
                    <button
                      type="button"
                      className="icon-btn"
                      aria-label="Dismiss"
                      onClick={() => library.dismissImport(job.id)}
                    >
                      <Icon name="x" size={16} />
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}

          {continueBook && (
            <button type="button" className="continue" onClick={() => open(continueBook)}>
              <Cover book={continueBook} className="continue__cover" />
              <div className="continue__meta">
                <p className="continue__eyebrow">Continue reading</p>
                <p className="continue__title">{continueBook.title}</p>
                <p className="continue__line">
                  {Math.round((progress[continueBook.id]?.percent ?? 0) * 100)}% through ·{' '}
                  {formatDuration(
                    continueBook.minutes * (1 - (progress[continueBook.id]?.percent ?? 0)),
                  )}{' '}
                  left
                </p>
              </div>
              <Icon name="chevronRight" size={20} />
            </button>
          )}

          {!loading && !visible.length ? (
            <div className="empty">
              <Icon name="book" size={30} />
              <h2>
                {query
                  ? 'Nothing matches that'
                  : isFirstRun
                    ? 'Read your PDFs like books.'
                    : 'Your shelf is empty'}
              </h2>
              <p>
                {query
                  ? 'Try a different title, author or file name.'
                  : isFirstRun
                    ? 'Drop a PDF here, or choose one below. No account needed — it stays on this device.'
                    : 'Drop a PDF anywhere on this page, or add one below. It is read on your device and stays there.'}
              </p>
              {!query && (
                <button type="button" className="btn btn--primary" onClick={pickFiles}>
                  <Icon name="upload" size={16} />
                  {isFirstRun ? 'Choose a PDF' : 'Add a PDF'}
                </button>
              )}
            </div>
          ) : (
            <div className="grid">
              {visible.map((book) => (
                <BookCard
                  key={book.id}
                  book={book}
                  percent={progress[book.id]?.percent ?? 0}
                  onDevice={local.has(book.id)}
                  onOpen={() => open(book)}
                  onMenu={(event, element) => {
                    setMenuBook(book)
                    if ('clientX' in event && event.clientX) menu.openAt(event)
                    else if (element) menu.openFrom(element)
                  }}
                />
              ))}
            </div>
          )}
        </div>
      </div>

      {dragging && (
        <div className="dropzone-overlay">
          <Icon name="download" size={30} />
          Drop your PDFs to add them
        </div>
      )}

      {menu.anchor && menuBook && (
        <Menu
          x={menu.anchor.x}
          y={menu.anchor.y}
          onClose={() => {
            menu.close()
            setMenuBook(null)
          }}
          items={[
            { label: 'Open', icon: 'book', run: () => open(menuBook) },
            { label: 'Move to folder…', icon: 'folder', run: () => setMoving(menuBook) },
            { label: 'Edit details…', icon: 'edit', run: () => setEditing(menuBook) },
            'separator',
            { label: 'Remove from library', icon: 'trash', danger: true, run: () => setDeleting(menuBook) },
          ]}
        />
      )}

      {folderMenu && (
        <Menu
          x={folderMenu.x}
          y={folderMenu.y}
          onClose={() => setFolderMenu(null)}
          items={[
            {
              label: 'Open folder',
              icon: 'folder',
              run: () => navigate({ name: 'library', folderId: folderMenu.id }),
            },
            { label: 'Rename…', icon: 'edit', run: () => setRenamingFolder(folderMenu.id) },
            'separator',
            { label: 'Delete folder', icon: 'trash', danger: true, run: () => setDeletingFolder(folderMenu.id) },
          ]}
        />
      )}

      <EditBookSheet book={editing} onClose={() => setEditing(null)} />
      <MoveSheet book={moving} onClose={() => setMoving(null)} />
      <NewFolderSheet open={newFolder} onClose={() => setNewFolder(false)} />

      <RenameFolderSheet
        folder={folders.find((folder) => folder.id === renamingFolder)}
        onClose={() => setRenamingFolder(null)}
      />
      <Confirm
        open={Boolean(deletingFolder)}
        title="Delete this folder?"
        body={
          <>
            <strong>{folders.find((folder) => folder.id === deletingFolder)?.name}</strong> will be
            deleted. The {plural(counts.map.get(deletingFolder ?? '') ?? 0, 'book')} inside move to
            Unsorted — nothing is lost.
          </>
        }
        confirmLabel="Delete folder"
        onConfirm={() => {
          if (!deletingFolder) return
          void library.removeFolder(deletingFolder)
          if (folderId === deletingFolder) navigate({ name: 'library', folderId: null })
        }}
        onClose={() => setDeletingFolder(null)}
      />

      <Confirm
        open={Boolean(deleting)}
        title="Remove this book?"
        body={
          <>
            <strong>{deleting?.title}</strong> and its highlights, notes and reading position will be
            removed from this device. The original PDF on your computer is untouched.
          </>
        }
        confirmLabel="Remove"
        onConfirm={() => {
          if (deleting) void library.removeBook(deleting.id)
          toast('Book removed.', 'info')
        }}
        onClose={() => setDeleting(null)}
      />
    </div>
  )
}

/* --------------------------------------------------------------- pieces -- */

function RailItem({
  active,
  label,
  icon,
  hue,
  count,
  onClick,
  onContext,
  onDropBook,
  isDropTarget,
  setDropTarget,
}: {
  active: boolean
  label: string
  icon?: 'book' | 'inbox'
  hue?: number
  count: number
  onClick: () => void
  onContext?: (event: React.MouseEvent) => void
  onDropBook?: (bookId: string) => void
  isDropTarget?: boolean
  setDropTarget?: (on: boolean) => void
}) {
  return (
    <button
      type="button"
      className={`rail__item${active ? ' is-active' : ''}${isDropTarget ? ' is-drop' : ''}`}
      onClick={onClick}
      onContextMenu={onContext}
      onDragOver={
        onDropBook
          ? (event) => {
              if (event.dataTransfer.types.includes('text/cozypdf-book')) {
                event.preventDefault()
                setDropTarget?.(true)
              }
            }
          : undefined
      }
      onDragLeave={onDropBook ? () => setDropTarget?.(false) : undefined}
      onDrop={
        onDropBook
          ? (event) => {
              event.preventDefault()
              setDropTarget?.(false)
              const id = event.dataTransfer.getData('text/cozypdf-book')
              if (id) onDropBook(id)
            }
          : undefined
      }
    >
      {icon ? (
        <Icon name={icon} size={16} />
      ) : (
        <span className="folder-dot" style={{ '--hue': hue ?? 30 } as never} />
      )}
      <span>{label}</span>
      <span className="rail__count">{count}</span>
    </button>
  )
}

function Cover({ book, className }: { book: Book; className?: string }) {
  if (book.cover) return <img className={className} src={book.cover} alt="" loading="lazy" />
  return (
    <div className={className} style={{ background: `hsl(${hueFrom(book.title)} 24% 32%)` }} />
  )
}

function BookCard({
  book,
  percent,
  onDevice,
  onOpen,
  onMenu,
}: {
  book: Book
  percent: number
  onDevice: boolean
  onOpen: () => void
  onMenu: (event: React.MouseEvent, element?: HTMLElement) => void
}) {
  const moreRef = useRef<HTMLButtonElement>(null)
  return (
    <div
      className={`book${onDevice ? '' : ' is-remote'}`}
      draggable
      onDragStart={(event) => {
        event.dataTransfer.setData('text/cozypdf-book', book.id)
        event.dataTransfer.effectAllowed = 'move'
      }}
      onContextMenu={(event) => {
        event.preventDefault()
        onMenu(event)
      }}
    >
      <button type="button" className="book__cover" onClick={onOpen} aria-label={`Open ${book.title}`}>
        {book.cover ? (
          <img src={book.cover} alt="" loading="lazy" />
        ) : (
          <span className="book__fallback" style={{ '--hue': hueFrom(book.title) } as never}>
            <span>{book.title}</span>
          </span>
        )}
        {!onDevice && <span className="book__badge">Not on this device</span>}
        {onDevice && book.scanned && <span className="book__badge">Scanned</span>}
        {percent > 0.005 && (
          <span className="book__bar">
            <i style={{ width: `${Math.min(100, percent * 100)}%` }} />
          </span>
        )}
      </button>
      <button
        type="button"
        className="book__more"
        ref={moreRef}
        aria-label={`More options for ${book.title}`}
        onClick={(event) => {
          event.stopPropagation()
          onMenu(event, moreRef.current ?? undefined)
        }}
      >
        <Icon name="more" size={16} strokeWidth={2.4} />
      </button>
      <div>
        <p className="book__title">{book.title}</p>
        <p className="book__author">
          {book.author || `${book.pageCount} pages · ${formatDuration(book.minutes)}`}
        </p>
      </div>
    </div>
  )
}

/* -------------------------------------------------------------- sheets -- */

function EditBookSheet({ book, onClose }: { book: Book | null; onClose: () => void }) {
  const { renameBook } = useLibrary()
  const [title, setTitle] = useState('')
  const [author, setAuthor] = useState('')

  useEffect(() => {
    setTitle(book?.title ?? '')
    setAuthor(book?.author ?? '')
  }, [book])

  return (
    <Sheet
      open={Boolean(book)}
      onClose={onClose}
      title="Edit details"
      footer={
        <>
          <button type="button" className="btn btn--ghost" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className="btn btn--primary"
            onClick={() => {
              if (book) void renameBook(book.id, title, author)
              onClose()
            }}
          >
            Save
          </button>
        </>
      }
    >
      <div className="sheet__body">
        <div className="field">
          <label className="field__label" htmlFor="edit-title">
            Title
          </label>
          <input
            id="edit-title"
            className="input"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
          />
        </div>
        <div className="field">
          <label className="field__label" htmlFor="edit-author">
            Author
          </label>
          <input
            id="edit-author"
            className="input"
            value={author}
            placeholder="Unknown"
            onChange={(event) => setAuthor(event.target.value)}
          />
        </div>
      </div>
    </Sheet>
  )
}

function MoveSheet({ book, onClose }: { book: Book | null; onClose: () => void }) {
  const { folders, moveBook, createFolder } = useLibrary()
  const [name, setName] = useState('')

  return (
    <Sheet open={Boolean(book)} onClose={onClose} title="Move to folder">
      <div className="sheet__body">
        <div className="font-row">
          <button
            type="button"
            className="font-option"
            aria-pressed={book?.folderId === null}
            onClick={() => {
              if (book) void moveBook(book.id, null)
              onClose()
            }}
          >
            <Icon name="inbox" size={16} />
            <span className="font-option__name">Unsorted</span>
          </button>
          {folders.map((folder) => (
            <button
              key={folder.id}
              type="button"
              className="font-option"
              aria-pressed={book?.folderId === folder.id}
              onClick={() => {
                if (book) void moveBook(book.id, folder.id)
                onClose()
              }}
            >
              <span className="folder-dot" style={{ '--hue': folder.hue } as never} />
              <span className="font-option__name">{folder.name}</span>
            </button>
          ))}
        </div>

        <div className="field">
          <label className="field__label" htmlFor="move-new">
            Or make a new one
          </label>
          <div style={{ display: 'flex', gap: 8 }}>
            <input
              id="move-new"
              className="input"
              value={name}
              placeholder="Novels, Research…"
              onChange={(event) => setName(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') void submit()
              }}
            />
            <button type="button" className="btn btn--outline" onClick={() => void submit()} disabled={!name.trim()}>
              Create
            </button>
          </div>
        </div>
      </div>
    </Sheet>
  )

  async function submit() {
    if (!name.trim() || !book) return
    const folder = await createFolder(name)
    await moveBook(book.id, folder.id)
    setName('')
    onClose()
  }
}

function NewFolderSheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { createFolder } = useLibrary()
  const [name, setName] = useState('')

  const submit = async () => {
    if (!name.trim()) return
    const folder = await createFolder(name)
    setName('')
    onClose()
    navigate({ name: 'library', folderId: folder.id })
  }

  return (
    <Sheet
      open={open}
      onClose={onClose}
      title="New folder"
      footer={
        <>
          <button type="button" className="btn btn--ghost" onClick={onClose}>
            Cancel
          </button>
          <button type="button" className="btn btn--primary" onClick={() => void submit()} disabled={!name.trim()}>
            Create folder
          </button>
        </>
      }
    >
      <div className="sheet__body">
        <div className="field">
          <label className="field__label" htmlFor="folder-name">
            Name
          </label>
          <input
            id="folder-name"
            className="input"
            value={name}
            placeholder="Novels, Research, To read…"
            onChange={(event) => setName(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') void submit()
            }}
          />
        </div>
      </div>
    </Sheet>
  )
}

function RenameFolderSheet({
  folder,
  onClose,
}: {
  folder: { id: string; name: string } | undefined
  onClose: () => void
}) {
  const { renameFolder } = useLibrary()
  const [name, setName] = useState('')

  useEffect(() => {
    setName(folder?.name ?? '')
  }, [folder])

  return (
    <Sheet
      open={Boolean(folder)}
      onClose={onClose}
      title="Rename folder"
      footer={
        <>
          <button type="button" className="btn btn--ghost" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className="btn btn--primary"
            onClick={() => {
              if (folder) void renameFolder(folder.id, name)
              onClose()
            }}
          >
            Save
          </button>
        </>
      }
    >
      <div className="sheet__body">
        <div className="field">
          <label className="field__label" htmlFor="folder-rename">
            Name
          </label>
          <input
            id="folder-rename"
            className="input"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </div>
      </div>
    </Sheet>
  )
}
