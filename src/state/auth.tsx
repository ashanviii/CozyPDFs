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
import { api, ApiError, getToken, setToken } from '../lib/api'
import { describeSyncError, lastSyncAt, resetSyncState, syncNow } from '../lib/sync'
import { wipeLocal } from '../lib/db'
import type { User } from '../lib/types'

type Status = 'unknown' | 'signed-out' | 'signed-in'
type SyncState = 'idle' | 'syncing' | 'error' | 'offline'

interface AuthContextValue {
  user: User | null
  status: Status
  syncState: SyncState
  syncMessage: string
  lastSync: number
  signIn: (email: string, password: string) => Promise<void>
  signUp: (name: string, email: string, password: string) => Promise<void>
  signOut: (options?: { clearDevice?: boolean }) => Promise<void>
  sync: (silent?: boolean) => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

const SYNC_INTERVAL = 2 * 60 * 1000

export function AuthProvider({ children, onLibraryChange }: { children: ReactNode; onLibraryChange: () => void }) {
  const [user, setUser] = useState<User | null>(null)
  const [status, setStatus] = useState<Status>(getToken() ? 'unknown' : 'signed-out')
  const [syncState, setSyncState] = useState<SyncState>('idle')
  const [syncMessage, setSyncMessage] = useState('')
  const [lastSync, setLastSync] = useState(0)
  const changeRef = useRef(onLibraryChange)
  changeRef.current = onLibraryChange

  const sync = useCallback(async (silent = true) => {
    if (!getToken()) return
    if (!navigator.onLine) {
      setSyncState('offline')
      setSyncMessage('Offline — reading works as normal.')
      return
    }
    setSyncState('syncing')
    try {
      const result = await syncNow()
      setSyncState('idle')
      setSyncMessage('')
      setLastSync(Date.now())
      if (result && result.pulled > 0) changeRef.current()
      if (!silent && result) {
        setSyncMessage(result.pulled || result.pushed ? 'Library up to date.' : 'Already up to date.')
      }
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        setToken(null)
        setUser(null)
        setStatus('signed-out')
      }
      setSyncState(error instanceof ApiError && error.status === 0 ? 'offline' : 'error')
      setSyncMessage(describeSyncError(error))
    }
  }, [])

  // Restore the session on boot.
  useEffect(() => {
    let cancelled = false
    if (!getToken()) return
    void (async () => {
      try {
        const { user: me } = await api.me()
        if (cancelled) return
        setUser(me)
        setStatus('signed-in')
        void sync()
      } catch (error) {
        if (cancelled) return
        if (error instanceof ApiError && error.status === 0) {
          // Offline: keep believing in the session until the server says no.
          setStatus('signed-in')
          setSyncState('offline')
        } else {
          setToken(null)
          setStatus('signed-out')
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [sync])

  useEffect(() => {
    void lastSyncAt().then(setLastSync)
  }, [])

  // Keep in step: on an interval, when the tab returns, and when we come back online.
  useEffect(() => {
    if (status !== 'signed-in') return
    const timer = window.setInterval(() => void sync(), SYNC_INTERVAL)
    const onVisible = () => {
      if (document.visibilityState === 'visible') void sync()
    }
    const onOnline = () => void sync()
    document.addEventListener('visibilitychange', onVisible)
    window.addEventListener('online', onOnline)
    return () => {
      clearInterval(timer)
      document.removeEventListener('visibilitychange', onVisible)
      window.removeEventListener('online', onOnline)
    }
  }, [status, sync])

  const afterAuth = useCallback(
    async (token: string, me: User) => {
      setToken(token)
      setUser(me)
      setStatus('signed-in')
      await resetSyncState() // a fresh session pulls the whole library
      await sync()
      changeRef.current()
    },
    [sync],
  )

  const signIn = useCallback(
    async (email: string, password: string) => {
      const { token, user: me } = await api.login({ email, password })
      await afterAuth(token, me)
    },
    [afterAuth],
  )

  const signUp = useCallback(
    async (name: string, email: string, password: string) => {
      const { token, user: me } = await api.signup({ name, email, password })
      await afterAuth(token, me)
    },
    [afterAuth],
  )

  const signOut = useCallback(async (options?: { clearDevice?: boolean }) => {
    setToken(null)
    setUser(null)
    setStatus('signed-out')
    setSyncState('idle')
    setSyncMessage('')
    await resetSyncState()
    if (options?.clearDevice) await wipeLocal()
    changeRef.current()
  }, [])

  const value = useMemo(
    () => ({ user, status, syncState, syncMessage, lastSync, signIn, signUp, signOut, sync }),
    [user, status, syncState, syncMessage, lastSync, signIn, signUp, signOut, sync],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside AuthProvider')
  return context
}
