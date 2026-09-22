import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import {
  allBooks,
  allFolders,
  allProgress,
  db,
  getBook,
  putBook,
  putFolder,
  putProgress,
  softDeleteBook,
  softDeleteFolder,
  getFile,
  putFile,
  putDoc,
  requestPersistence,
} from '../lib/db'
import { extractBook, type ExtractPhase } from '../lib/pdf'
import { getToken } from '../lib/api'
import { syncNow } from '../lib/sync'
import type { Book, Folder, Progress } from '../lib/types'
import { hueFrom, titleFromFileName, uid } from '../lib/util'
import { useToast } from './toast'

export interface ImportJob {
  id: string
  name: string
  phase: ExtractPhase | 'queued' | 'saving' | 'failed'
  done: number
  total: number
  error?: string
}

interface LibraryContextValue {
  books: Book[]
  folders: Folder[]
  progress: Record<string, Progress>
  /** Book ids whose PDF is present on this device. */
  local: Set<string>
  loading: boolean
  imports: ImportJob[]
  refresh: () => Promise<void>
  addFiles: (files: File[]) => Promise<void>
  dismissImport: (id: string) => void
  createFolder: (name: string) => Promise<Folder>
  renameFolder: (id: string, name: string) => Promise<void>
  removeFolder: (id: string) => Promise<void>
  moveBook: (bookId: string, folderId: string | null) => Promise<void>
  renameBook: (bookId: string, title: string, author: string) => Promise<void>
  removeBook: (bookId: string) => Promise<void>
  touchBook: (bookId: string) => Promise<void>
  saveProgress: (progress: Progress) => Promise<void>
}

const LibraryContext = createContext<LibraryContextValue | null>(null)

const PHASE_TOTALS: Record<string, string> = {
  queued: 'Waiting',
  opening: 'Opening',
  reading: 'Reading pages',
  shaping: 'Finding paragraphs',
  cover: 'Making a cover',
  saving: 'Saving',
  done: 'Ready',
  failed: 'Failed',
}

export const describePhase = (job: ImportJob) => PHASE_TOTALS[job.phase] ?? 'Working'

export function LibraryProvider({ children }: { children: ReactNode }) {
  const [books, setBooks] = useState<Book[]>([])
  const [folders, setFolders] = useState<Folder[]>([])
  const [progress, setProgress] = useState<Record<string, Progress>>({})
  const [local, setLocal] = useState<Set<string>>(new Set())
  const [loading, setLoading] = useState(true)
  const [imports, setImports] = useState<ImportJob[]>([])
  const toast = useToast()
  const syncTimer = useRef<number>()

  const refresh = useCallback(async () => {
    const [nextBooks, nextFolders, progressRows, fileKeys] = await Promise.all([
      allBooks(),
      allFolders(),
      allProgress(),
      db().then((database) => database.getAllKeys('files')),
    ])
    nextBooks.sort((a, b) => (b.lastOpenedAt ?? b.addedAt) - (a.lastOpenedAt ?? a.addedAt))
    setBooks(nextBooks)
    setFolders(nextFolders)
    setProgress(Object.fromEntries(progressRows.map((row) => [row.bookId, row])))
    setLocal(new Set(fileKeys as string[]))
    setLoading(false)
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  /** Sync is a background nicety; never let it block a local write. */
  const scheduleSync = useCallback(() => {
    if (!getToken()) return
    window.clearTimeout(syncTimer.current)
    syncTimer.current = window.setTimeout(() => {
      void syncNow().catch(() => undefined)
    }, 1500)
  }, [])

  /* ------------------------------------------------------------ import ---- */

  const updateJob = useCallback((id: string, patch: Partial<ImportJob>) => {
    setImports((current) => current.map((job) => (job.id === id ? { ...job, ...patch } : job)))
  }, [])

  const dismissImport = useCallback((id: string) => {
    setImports((current) => current.filter((job) => job.id !== id))
  }, [])

  const addFiles = useCallback(
    async (files: File[]) => {
      const pdfs = files.filter(
        (file) => file.type === 'application/pdf' || /\.pdf$/i.test(file.name),
      )
      if (!pdfs.length) {
        toast('Those files are not PDFs. cozypdf reads PDFs only.', 'warn')
        return
      }
      if (pdfs.length !== files.length) {
        toast(`Skipped ${files.length - pdfs.length} file(s) that were not PDFs.`, 'warn')
      }

      void requestPersistence()

      const jobs: ImportJob[] = pdfs.map((file) => ({
        id: uid(),
        name: file.name,
        phase: 'queued',
        done: 0,
        total: 1,
      }))
      setImports((current) => [...current, ...jobs])

      // One at a time: PDF parsing is memory-hungry and this keeps the UI calm.
      for (let index = 0; index < pdfs.length; index++) {
        const file = pdfs[index]
        const job = jobs[index]
        try {
          const existing = (await allBooks()).find(
            (book) => book.fileName === file.name && book.fileSize === file.size,
          )
          const hasBytes = existing ? Boolean(await getFile(existing.id)) : false
          if (existing && hasBytes) {
            updateJob(job.id, { phase: 'done', done: 1 })
            toast(`"${existing.title}" is already in your library.`, 'info')
            window.setTimeout(() => dismissImport(job.id), 1200)
            continue
          }

          updateJob(job.id, { phase: 'opening' })
          const buffer = await file.arrayBuffer()
          const result = await extractBook(buffer, titleFromFileName(file.name), (update) => {
            updateJob(job.id, { phase: update.phase, done: update.done, total: update.total })
          })

          updateJob(job.id, { phase: 'saving', done: 1, total: 1 })
          // Adopting an existing record means a book synced from another device
          // simply gains its file here instead of being duplicated.
          const id = existing?.id ?? uid()
          await putFile({ bookId: id, blob: new Blob([buffer], { type: 'application/pdf' }) })
          await putDoc({ bookId: id, version: 1, blocks: result.blocks, chapters: result.chapters })

          const now = Date.now()
          await putBook({
            id,
            title: existing?.title ?? result.title ?? titleFromFileName(file.name),
            author: existing?.author ?? result.author ?? '',
            folderId: existing?.folderId ?? null,
            fileName: file.name,
            fileSize: file.size,
            pageCount: result.pageCount,
            wordCount: result.wordCount,
            minutes: Math.round(result.wordCount / 230),
            cover: result.cover ?? existing?.cover,
            scanned: result.scanned,
            addedAt: existing?.addedAt ?? now,
            lastOpenedAt: existing?.lastOpenedAt,
            updatedAt: now,
          })

          updateJob(job.id, { phase: 'done' })
          if (result.scanned) {
            toast(
              `"${result.title}" has no text layer, so it opens as page images.`,
              'warn',
            )
          }
          window.setTimeout(() => dismissImport(job.id), 1500)
          await refresh()
        } catch (error) {
          console.error('import failed', error)
          const message =
            error instanceof Error && /password|encrypted/i.test(error.message)
              ? 'This PDF is password protected.'
              : 'This PDF could not be read.'
          updateJob(job.id, { phase: 'failed', error: message })
          toast(`${file.name}: ${message}`, 'error')
        }
      }

      await refresh()
      scheduleSync()
    },
    [dismissImport, refresh, scheduleSync, toast, updateJob],
  )

  /* -------------------------------------------------------------- CRUD ---- */

  const createFolder = useCallback(
    async (name: string) => {
      const trimmed = name.trim().slice(0, 48) || 'New folder'
      const now = Date.now()
      const folder: Folder = {
        id: uid(),
        name: trimmed,
        hue: hueFrom(trimmed),
        order: folders.length,
        createdAt: now,
        updatedAt: now,
      }
      await putFolder(folder)
      await refresh()
      scheduleSync()
      return folder
    },
    [folders.length, refresh, scheduleSync],
  )

  const renameFolder = useCallback(
    async (id: string, name: string) => {
      const folder = folders.find((f) => f.id === id)
      if (!folder) return
      await putFolder({ ...folder, name: name.trim().slice(0, 48) || folder.name, updatedAt: Date.now() })
      await refresh()
      scheduleSync()
    },
    [folders, refresh, scheduleSync],
  )

  const removeFolder = useCallback(
    async (id: string) => {
      await softDeleteFolder(id)
      await refresh()
      scheduleSync()
    },
    [refresh, scheduleSync],
  )

  const moveBook = useCallback(
    async (bookId: string, folderId: string | null) => {
      const book = await getBook(bookId)
      if (!book) return
      await putBook({ ...book, folderId, updatedAt: Date.now() })
      await refresh()
      scheduleSync()
    },
    [refresh, scheduleSync],
  )

  const renameBook = useCallback(
    async (bookId: string, title: string, author: string) => {
      const book = await getBook(bookId)
      if (!book) return
      await putBook({
        ...book,
        title: title.trim().slice(0, 200) || book.title,
        author: author.trim().slice(0, 120),
        updatedAt: Date.now(),
      })
      await refresh()
      scheduleSync()
    },
    [refresh, scheduleSync],
  )

  const removeBook = useCallback(
    async (bookId: string) => {
      await softDeleteBook(bookId)
      await refresh()
      scheduleSync()
    },
    [refresh, scheduleSync],
  )

  const touchBook = useCallback(
    async (bookId: string) => {
      const book = await getBook(bookId)
      if (!book) return
      const now = Date.now()
      await putBook({ ...book, lastOpenedAt: now, updatedAt: now })
      setBooks((current) =>
        current.map((item) => (item.id === bookId ? { ...item, lastOpenedAt: now } : item)),
      )
    },
    [],
  )

  const saveProgress = useCallback(
    async (next: Progress) => {
      await putProgress(next)
      setProgress((current) => ({ ...current, [next.bookId]: next }))
      scheduleSync()
    },
    [scheduleSync],
  )

  const value = useMemo(
    () => ({
      books,
      folders,
      progress,
      local,
      loading,
      imports,
      refresh,
      addFiles,
      dismissImport,
      createFolder,
      renameFolder,
      removeFolder,
      moveBook,
      renameBook,
      removeBook,
      touchBook,
      saveProgress,
    }),
    [
      books,
      folders,
      progress,
      local,
      loading,
      imports,
      refresh,
      addFiles,
      dismissImport,
      createFolder,
      renameFolder,
      removeFolder,
      moveBook,
      renameBook,
      removeBook,
      touchBook,
      saveProgress,
    ],
  )

  return <LibraryContext.Provider value={value}>{children}</LibraryContext.Provider>
}

export function useLibrary() {
  const context = useContext(LibraryContext)
  if (!context) throw new Error('useLibrary must be used inside LibraryProvider')
  return context
}
