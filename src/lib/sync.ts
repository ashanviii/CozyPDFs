/**
 * Library sync.
 *
 * The device is always the source of truth for *reading*: everything works
 * signed out and offline. When signed in we exchange small records — folders,
 * book metadata, highlights, notes, reading positions — and merge them with
 * last-write-wins on `updatedAt`. PDF bytes never go over the wire.
 */
import { api, ApiError } from './api'
import { db, getMeta, setMeta } from './db'
import type { Annotation, Book, Folder, Progress } from './types'

const SINCE_KEY = 'sync.since'
const PUSHED_KEY = 'sync.pushedAt'
/** Slack for clock skew between devices, so nothing slips through a window. */
const GRACE = 5 * 60 * 1000

export interface SyncResult {
  pulled: number
  pushed: number
  at: number
}

let inFlight: Promise<SyncResult | null> | null = null

export function isSyncing() {
  return inFlight !== null
}

export async function syncNow(force = false): Promise<SyncResult | null> {
  if (inFlight && !force) return inFlight
  inFlight = run().finally(() => {
    inFlight = null
  })
  return inFlight
}

async function run(): Promise<SyncResult | null> {
  if (!navigator.onLine) return null

  const database = await db()
  const since = (await getMeta<number>(SINCE_KEY)) ?? 0
  const pushedAt = (await getMeta<number>(PUSHED_KEY)) ?? 0

  /* ------------------------------------------------------------- pull ---- */

  const remote = await api.pull(Math.max(0, since - GRACE))
  let pulled = 0

  const applyRecord = async (
    store: 'folders' | 'books' | 'annotations' | 'progress',
    key: string,
    record: Record<string, unknown>,
  ) => {
    const incoming = Number(record.updatedAt ?? 0)
    if (!incoming) return
    const existing = (await database.get(store, key)) as { updatedAt?: number } | undefined
    if (existing && Number(existing.updatedAt ?? 0) >= incoming) return
    // Covers are rendered locally and never uploaded, so never let a pull
    // wipe one we already have.
    const merged =
      store === 'books' && existing
        ? { ...record, cover: (existing as unknown as Book).cover ?? (record as unknown as Book).cover }
        : record
    await database.put(store, merged as never)
    pulled++
  }

  for (const folder of remote.folders as Folder[]) {
    if (folder?.id) await applyRecord('folders', folder.id, folder as never)
  }
  for (const book of remote.books as Book[]) {
    if (book?.id) await applyRecord('books', book.id, book as never)
  }
  for (const annotation of remote.annotations as Annotation[]) {
    if (annotation?.id) await applyRecord('annotations', annotation.id, annotation as never)
  }
  for (const progress of remote.progress as Progress[]) {
    if (progress?.bookId) await applyRecord('progress', progress.bookId, progress as never)
  }

  /* ------------------------------------------------------------- push ---- */

  const cutoff = Math.max(0, pushedAt - GRACE)
  const changed = <T extends { updatedAt: number }>(rows: T[]) =>
    rows.filter((row) => Number(row.updatedAt ?? 0) > cutoff)

  const books = changed(await database.getAll('books'))
  const payload = {
    folders: changed(await database.getAll('folders')),
    // The cover is a data URL; it stays local.
    books: books.map(({ cover, ...rest }) => rest),
    annotations: changed(await database.getAll('annotations')),
    progress: changed(await database.getAll('progress')),
  }

  const total =
    payload.folders.length + payload.books.length + payload.annotations.length + payload.progress.length

  let pushed = 0
  let now = remote.now
  if (total > 0) {
    const result = await api.push(payload)
    pushed = result.applied
    now = result.now
  }

  await setMeta(SINCE_KEY, remote.now)
  await setMeta(PUSHED_KEY, Date.now())
  await setMeta('sync.lastAt', Date.now())

  return { pulled, pushed, at: now }
}

/** Clears the sync watermarks so the next sync re-reads everything. */
export async function resetSyncState() {
  await setMeta(SINCE_KEY, 0)
  await setMeta(PUSHED_KEY, 0)
}

export async function lastSyncAt() {
  return (await getMeta<number>('sync.lastAt')) ?? 0
}

export function describeSyncError(error: unknown) {
  if (error instanceof ApiError) {
    if (error.status === 0) return 'Offline — your library is safe on this device.'
    if (error.status === 401) return 'Session expired. Sign in again to keep syncing.'
    return error.message
  }
  return 'Sync could not finish. Nothing was lost.'
}
