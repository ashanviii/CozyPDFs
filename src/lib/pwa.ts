import { useEffect, useState } from 'react'

interface InstallPromptEvent extends Event {
  prompt: () => Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>
}

let deferred: InstallPromptEvent | null = null
const listeners = new Set<(available: boolean) => void>()

if (typeof window !== 'undefined') {
  window.addEventListener('beforeinstallprompt', (event) => {
    event.preventDefault()
    deferred = event as InstallPromptEvent
    listeners.forEach((listener) => listener(true))
  })
  window.addEventListener('appinstalled', () => {
    deferred = null
    listeners.forEach((listener) => listener(false))
  })
}

export const isStandalone = () =>
  typeof window !== 'undefined' &&
  (matchMedia('(display-mode: standalone)').matches ||
    (navigator as unknown as { standalone?: boolean }).standalone === true)

/** Exposes the browser's install prompt when one is on offer. */
export function useInstallPrompt() {
  const [available, setAvailable] = useState(Boolean(deferred))

  useEffect(() => {
    listeners.add(setAvailable)
    return () => {
      listeners.delete(setAvailable)
    }
  }, [])

  const install = async () => {
    if (!deferred) return false
    await deferred.prompt()
    const { outcome } = await deferred.userChoice
    deferred = null
    setAvailable(false)
    return outcome === 'accepted'
  }

  return { available: available && !isStandalone(), install }
}

/** True while the browser reports no network. */
export function useOnline() {
  const [online, setOnline] = useState(() => navigator.onLine)
  useEffect(() => {
    const up = () => setOnline(true)
    const down = () => setOnline(false)
    window.addEventListener('online', up)
    window.addEventListener('offline', down)
    return () => {
      window.removeEventListener('online', up)
      window.removeEventListener('offline', down)
    }
  }, [])
  return online
}

/** Keeps the screen on while Listen Mode is playing, where supported. */
export function useWakeLock(active: boolean) {
  useEffect(() => {
    if (!active || !('wakeLock' in navigator)) return
    let sentinel: WakeLockSentinel | null = null
    let cancelled = false

    const request = async () => {
      try {
        sentinel = await navigator.wakeLock.request('screen')
      } catch {
        /* denied or unsupported; not worth telling the reader about */
      }
    }
    const onVisible = () => {
      if (document.visibilityState === 'visible' && !cancelled) void request()
    }

    void request()
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      cancelled = true
      document.removeEventListener('visibilitychange', onVisible)
      void sentinel?.release().catch(() => undefined)
    }
  }, [active])
}
