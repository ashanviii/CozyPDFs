/**
 * Local-first storage. Every read in the app goes through here; the network is
 * only ever a second opinion.
 */
import { openDB, type DBSchema, type IDBPDatabase } from 'idb'
import type { Annotation, Book, BookDoc, BookFile, Folder, Progress } from './types'

interface CozySchema extends DBSchema {
  books: { key: string; value: Book; indexes: { folderId: string; updatedAt: number } }
  folders: { key: string; value: Folder; indexes: { updatedAt: number } }
  docs: { key: string; value: BookDoc }
  files: { key: string; value: BookFile }
  annotations: {
    key: string
    value: Annotation
    indexes: { bookId: string; updatedAt: number; bookKind: [string, string] }
  }
  progress: { key: string; value: Progress; indexes: { updatedAt: number } }
  meta: { key: string; value: unknown }
}

const DB_NAME = 'cozypdf'
const DB_VERSION = 1

let dbPromise: Promise<IDBPDatabase<CozySchema>> | null = null

export function db() {
  if (!dbPromise) {
    dbPromise = openDB<CozySchema>(DB_NAME, DB_VERSION, {
      upgrade(database) {
        const books = database.createObjectStore('books', { keyPath: 'id' })
        books.createIndex('folderId', 'folderId')
        books.createIndex('updatedAt', 'updatedAt')

        const folders = database.createObjectStore('folders', { keyPath: 'id' })
        folders.createIndex('updatedAt', 'updatedAt')

        database.createObjectStore('docs', { keyPath: 'bookId' })
        database.createObjectStore('files', { keyPath: 'bookId' })

        const annotations = database.createObjectStore('annotations', { keyPath: 'id' })
        annotations.createIndex('bookId', 'bookId')
        annotations.createIndex('updatedAt', 'updatedAt')
        annotations.createIndex('bookKind', ['bookId', 'kind'])

        const progress = database.createObjectStore('progress', { keyPath: 'bookId' })
        progress.createIndex('updatedAt', 'updatedAt')

        database.createObjectStore('meta')
      },
    })
  }
  return dbPromise
}

/* --------------------------------------------------------------- books ---- */

export async function allBooks(): Promise<Book[]> {
  const rows = await (await db()).getAll('books')
  return rows.filter((b) => !b.deleted)
}

export async function getBook(id: string) {
  return (await db()).get('books', id)
}

export async function putBook(book: Book) {
  await (await db()).put('books', book)
  return book
}

export async function softDeleteBook(id: string) {
  const database = await db()
  const book = await database.get('books', id)
  if (!book) return
  await database.put('books', { ...book, deleted: true, updatedAt: Date.now() })
  // The heavy records go immediately — tombstones only need the metadata.
  await database.delete('docs', id)
  await database.delete('files', id)
  const notes = await database.getAllFromIndex('annotations', 'bookId', id)
  const tx = database.transaction('annotations', 'readwrite')
  await Promise.all(
    notes.map((n) => tx.store.put({ ...n, deleted: true, updatedAt: Date.now() })),
  )
  await tx.done
}

/* ------------------------------------------------------------- folders ---- */

export async function allFolders(): Promise<Folder[]> {
  const rows = await (await db()).getAll('folders')
  return rows.filter((f) => !f.deleted).sort((a, b) => a.order - b.order)
}

export async function putFolder(folder: Folder) {
  await (await db()).put('folders', folder)
  return folder
}

export async function softDeleteFolder(id: string) {
  const database = await db()
  const folder = await database.get('folders', id)
  if (folder) await database.put('folders', { ...folder, deleted: true, updatedAt: Date.now() })
  // Books in a deleted folder fall back to Unsorted rather than disappearing.
  const books = await database.getAllFromIndex('books', 'folderId', id)
  const tx = database.transaction('books', 'readwrite')
  await Promise.all(
    books.map((b) => tx.store.put({ ...b, folderId: null, updatedAt: Date.now() })),
  )
  await tx.done
}

/* ---------------------------------------------------------- doc + file ---- */

export async function getDoc(bookId: string) {
  return (await db()).get('docs', bookId)
}

export async function putDoc(doc: BookDoc) {
  await (await db()).put('docs', doc)
}

export async function getFile(bookId: string) {
  return (await db()).get('files', bookId)
}

export async function putFile(file: BookFile) {
  await (await db()).put('files', file)
}

/* --------------------------------------------------------- annotations ---- */

export async function annotationsFor(bookId: string): Promise<Annotation[]> {
  const rows = await (await db()).getAllFromIndex('annotations', 'bookId', bookId)
  return rows.filter((a) => !a.deleted).sort((a, b) => a.blockIndex - b.blockIndex || a.start - b.start)
}

export async function allAnnotations(): Promise<Annotation[]> {
  return (await db()).getAll('annotations')
}

export async function putAnnotation(annotation: Annotation) {
  await (await db()).put('annotations', annotation)
  return annotation
}

export async function deleteAnnotation(id: string) {
  const database = await db()
  const existing = await database.get('annotations', id)
  if (!existing) return
  await database.put('annotations', { ...existing, deleted: true, updatedAt: Date.now() })
}

/* ------------------------------------------------------------ progress ---- */

export async function getProgress(bookId: string) {
  return (await db()).get('progress', bookId)
}

export async function allProgress(): Promise<Progress[]> {
  return (await db()).getAll('progress')
}

export async function putProgress(progress: Progress) {
  await (await db()).put('progress', progress)
}

/* ---------------------------------------------------------------- meta ---- */

export async function getMeta<T>(key: string): Promise<T | undefined> {
  return (await db()).get('meta', key) as Promise<T | undefined>
}

export async function setMeta(key: string, value: unknown) {
  await (await db()).put('meta', value, key)
}

/** Rough on-disk footprint, for the storage line in Settings. */
export async function estimateUsage() {
  if (!navigator.storage?.estimate) return null
  const { usage = 0, quota = 0 } = await navigator.storage.estimate()
  return { usage, quota }
}

/** Ask the browser not to evict the library under storage pressure. */
export async function requestPersistence() {
  if (!navigator.storage?.persist) return false
  if (await navigator.storage.persisted?.()) return true
  return navigator.storage.persist()
}

/** Wipes everything. Used by "Sign out and clear this device". */
export async function wipeLocal() {
  const database = await db()
  await Promise.all(
    (['books', 'folders', 'docs', 'files', 'annotations', 'progress', 'meta'] as const).map((s) =>
      database.clear(s),
    ),
  )
}
