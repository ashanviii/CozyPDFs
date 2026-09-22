/**
 * cozypdf sync server.
 *
 * Deliberately small. The app is complete without it — this only keeps a
 * logged-in reader's library metadata, folders, highlights, notes and reading
 * positions in step across devices. PDF files never leave the device.
 *
 * Only dependency is express; storage is Node's built-in SQLite and crypto.
 */
import { createRequire } from 'node:module'
import { randomBytes, randomUUID, scrypt, timingSafeEqual, createHmac } from 'node:crypto'
import { promisify } from 'node:util'
import { mkdirSync, existsSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import express from 'express'

const require = createRequire(import.meta.url)
const { DatabaseSync } = require('node:sqlite')

const scryptAsync = promisify(scrypt)
const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const DATA_DIR = process.env.COZYPDF_DATA ?? resolve(ROOT, '.data')
// An explicit argument wins, so `npm run dev` is never confused by a PORT
// that belongs to something else in the environment.
const PORT = Number(process.argv[2] ?? process.env.COZYPDF_PORT ?? process.env.PORT ?? 8787)
const TOKEN_TTL = 1000 * 60 * 60 * 24 * 60 // 60 days

mkdirSync(DATA_DIR, { recursive: true })

/* ---------------------------------------------------------------- secret -- */

const secretPath = resolve(DATA_DIR, 'secret.key')
if (!existsSync(secretPath)) writeFileSync(secretPath, randomBytes(48).toString('hex'), { mode: 0o600 })
const SECRET = process.env.COZYPDF_SECRET ?? readFileSync(secretPath, 'utf8').trim()

/* -------------------------------------------------------------- database -- */

const db = new DatabaseSync(resolve(DATA_DIR, 'cozypdf.db'))
db.exec(`
  PRAGMA journal_mode = WAL;
  CREATE TABLE IF NOT EXISTS users (
    id          TEXT PRIMARY KEY,
    email       TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    password    TEXT NOT NULL,
    created_at  INTEGER NOT NULL
  );
  CREATE TABLE IF NOT EXISTS records (
    user_id     TEXT NOT NULL,
    kind        TEXT NOT NULL,
    id          TEXT NOT NULL,
    updated_at  INTEGER NOT NULL,
    body        TEXT NOT NULL,
    PRIMARY KEY (user_id, kind, id)
  );
  CREATE INDEX IF NOT EXISTS records_since ON records (user_id, updated_at);
`)

const q = {
  userByEmail: db.prepare('SELECT * FROM users WHERE email = ?'),
  userById: db.prepare('SELECT * FROM users WHERE id = ?'),
  insertUser: db.prepare(
    'INSERT INTO users (id, email, name, password, created_at) VALUES (?, ?, ?, ?, ?)',
  ),
  since: db.prepare(
    'SELECT kind, id, updated_at, body FROM records WHERE user_id = ? AND updated_at > ? ORDER BY updated_at',
  ),
  one: db.prepare('SELECT updated_at FROM records WHERE user_id = ? AND kind = ? AND id = ?'),
  upsert: db.prepare(
    `INSERT INTO records (user_id, kind, id, updated_at, body) VALUES (?, ?, ?, ?, ?)
     ON CONFLICT(user_id, kind, id) DO UPDATE SET updated_at = excluded.updated_at, body = excluded.body`,
  ),
  wipe: db.prepare('DELETE FROM records WHERE user_id = ?'),
  dropUser: db.prepare('DELETE FROM users WHERE id = ?'),
}

/* -------------------------------------------------------- auth utilities -- */

const b64url = (buf) => Buffer.from(buf).toString('base64url')

async function hashPassword(password) {
  const salt = randomBytes(16)
  const key = await scryptAsync(password, salt, 64, { N: 16384, r: 8, p: 1 })
  return `scrypt$${salt.toString('base64')}$${key.toString('base64')}`
}

async function verifyPassword(password, stored) {
  const [scheme, saltB64, keyB64] = String(stored).split('$')
  if (scheme !== 'scrypt') return false
  const salt = Buffer.from(saltB64, 'base64')
  const expected = Buffer.from(keyB64, 'base64')
  const actual = await scryptAsync(password, salt, expected.length, { N: 16384, r: 8, p: 1 })
  return expected.length === actual.length && timingSafeEqual(expected, actual)
}

function signToken(userId) {
  const payload = b64url(JSON.stringify({ sub: userId, exp: Date.now() + TOKEN_TTL }))
  const mac = createHmac('sha256', SECRET).update(payload).digest('base64url')
  return `${payload}.${mac}`
}

function verifyToken(token) {
  if (typeof token !== 'string' || !token.includes('.')) return null
  const [payload, mac] = token.split('.')
  const expected = createHmac('sha256', SECRET).update(payload).digest('base64url')
  const a = Buffer.from(mac ?? '')
  const b = Buffer.from(expected)
  if (a.length !== b.length || !timingSafeEqual(a, b)) return null
  try {
    const data = JSON.parse(Buffer.from(payload, 'base64url').toString('utf8'))
    if (!data?.sub || typeof data.exp !== 'number' || data.exp < Date.now()) return null
    return data.sub
  } catch {
    return null
  }
}

const publicUser = (row) => ({
  id: row.id,
  email: row.email,
  name: row.name,
  createdAt: row.created_at,
})

/* ------------------------------------------------------------------ app -- */

const app = express()
app.disable('x-powered-by')
app.use(express.json({ limit: '12mb' }))

app.use('/api', (_req, res, next) => {
  res.set('Cache-Control', 'no-store')
  next()
})

function requireAuth(req, res, next) {
  const header = req.get('authorization') ?? ''
  const userId = verifyToken(header.replace(/^Bearer\s+/i, ''))
  if (!userId) return res.status(401).json({ error: 'Please sign in again.' })
  const row = q.userById.get(userId)
  if (!row) return res.status(401).json({ error: 'Please sign in again.' })
  req.user = row
  next()
}

/* -------------------------------------------------------- simple limiter -- */

const attempts = new Map()
function rateLimit(key, max, windowMs) {
  const now = Date.now()
  const entry = attempts.get(key)
  if (!entry || now > entry.reset) {
    attempts.set(key, { count: 1, reset: now + windowMs })
    return true
  }
  entry.count++
  return entry.count <= max
}
setInterval(() => {
  const now = Date.now()
  for (const [key, entry] of attempts) if (now > entry.reset) attempts.delete(key)
}, 60_000).unref?.()

/* ----------------------------------------------------------------- auth -- */

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/

app.post('/api/auth/signup', async (req, res) => {
  const email = String(req.body?.email ?? '').trim().toLowerCase()
  const name = String(req.body?.name ?? '').trim().slice(0, 60)
  const password = String(req.body?.password ?? '')

  if (!EMAIL_RE.test(email)) return res.status(400).json({ error: 'That email does not look right.' })
  if (password.length < 8)
    return res.status(400).json({ error: 'Use at least 8 characters for your password.' })
  if (q.userByEmail.get(email)) return res.status(409).json({ error: 'That email is already registered.' })

  const user = {
    id: randomUUID(),
    email,
    name: name || email.split('@')[0],
    created_at: Date.now(),
  }
  q.insertUser.run(user.id, user.email, user.name, await hashPassword(password), user.created_at)
  res.json({ token: signToken(user.id), user: publicUser(user) })
})

app.post('/api/auth/login', async (req, res) => {
  const email = String(req.body?.email ?? '').trim().toLowerCase()
  const password = String(req.body?.password ?? '')
  const key = `${req.ip}|${email}`
  if (!rateLimit(key, 10, 10 * 60_000))
    return res.status(429).json({ error: 'Too many attempts. Try again in a few minutes.' })

  const row = q.userByEmail.get(email)
  const ok = row ? await verifyPassword(password, row.password) : false
  if (!row || !ok) return res.status(401).json({ error: 'Email or password is incorrect.' })
  res.json({ token: signToken(row.id), user: publicUser(row) })
})

app.get('/api/auth/me', requireAuth, (req, res) => {
  res.json({ user: publicUser(req.user) })
})

/* ----------------------------------------------------------------- sync -- */

const KINDS = ['folders', 'books', 'annotations', 'progress']
const idOf = (kind, record) => (kind === 'progress' ? record.bookId : record.id)

app.get('/api/sync', requireAuth, (req, res) => {
  const since = Number(req.query.since ?? 0) || 0
  const out = { folders: [], books: [], annotations: [], progress: [] }
  for (const row of q.since.all(req.user.id, since)) {
    if (!out[row.kind]) continue
    try {
      out[row.kind].push(JSON.parse(row.body))
    } catch {
      /* skip a corrupt row rather than failing the whole pull */
    }
  }
  res.json({ now: Date.now(), ...out })
})

app.post('/api/sync', requireAuth, (req, res) => {
  const body = req.body ?? {}
  let applied = 0
  let skipped = 0

  db.exec('BEGIN')
  try {
    for (const kind of KINDS) {
      const records = Array.isArray(body[kind]) ? body[kind] : []
      for (const record of records) {
        const id = idOf(kind, record)
        if (!id || typeof id !== 'string') continue
        const updatedAt = Number(record.updatedAt ?? 0)
        if (!Number.isFinite(updatedAt) || updatedAt <= 0) continue
        const existing = q.one.get(req.user.id, kind, id)
        // Last write wins; a tie keeps what the server already has.
        if (existing && existing.updated_at >= updatedAt) {
          skipped++
          continue
        }
        const clean = kind === 'books' ? { ...record, cover: undefined } : record
        q.upsert.run(req.user.id, kind, id, updatedAt, JSON.stringify(clean))
        applied++
      }
    }
    db.exec('COMMIT')
  } catch (error) {
    db.exec('ROLLBACK')
    console.error('sync failed', error)
    return res.status(500).json({ error: 'Could not save your changes. They are still on this device.' })
  }

  res.json({ now: Date.now(), applied, skipped })
})

app.delete('/api/account', requireAuth, (req, res) => {
  q.wipe.run(req.user.id)
  q.dropUser.run(req.user.id)
  res.json({ ok: true })
})

app.get('/api/health', (_req, res) => res.json({ ok: true, now: Date.now() }))

/* ---------------------------------------------- static build, if present -- */

const dist = resolve(ROOT, 'dist')
if (existsSync(dist)) {
  app.use(express.static(dist, { maxAge: '1h', index: false }))
  app.get('*', (req, res, next) => {
    if (req.path.startsWith('/api/')) return next()
    res.sendFile(resolve(dist, 'index.html'))
  })
}

app.use('/api', (_req, res) => res.status(404).json({ error: 'Not found' }))

app.listen(PORT, () => {
  console.log(`cozypdf sync listening on http://localhost:${PORT}`)
  console.log(`data directory: ${DATA_DIR}`)
  if (!existsSync(dist)) console.log('(run "npm run build" to also serve the app from here)')
})
