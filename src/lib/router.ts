/**
 * A tiny hash router. Hash routing keeps the app working when it is opened
 * from a file, a service-worker cache, or an installed PWA window.
 */
import { useEffect, useState } from 'react'

export type Route =
  | { name: 'library'; folderId: string | null }
  | { name: 'reader'; bookId: string }
  | { name: 'auth'; mode: 'login' | 'signup' }
  | { name: 'settings' }

export function parseHash(hash: string): Route {
  const path = hash.replace(/^#\/?/, '').split('?')[0]
  const [head, tail] = path.split('/')
  switch (head) {
    case 'read':
      return tail ? { name: 'reader', bookId: decodeURIComponent(tail) } : { name: 'library', folderId: null }
    case 'folder':
      return { name: 'library', folderId: tail ? decodeURIComponent(tail) : null }
    case 'unsorted':
      return { name: 'library', folderId: '__unsorted__' }
    case 'signin':
    case 'login':
      return { name: 'auth', mode: 'login' }
    case 'signup':
      return { name: 'auth', mode: 'signup' }
    case 'settings':
      return { name: 'settings' }
    default:
      return { name: 'library', folderId: null }
  }
}

export function hashFor(route: Route) {
  switch (route.name) {
    case 'reader':
      return `#/read/${encodeURIComponent(route.bookId)}`
    case 'auth':
      return route.mode === 'signup' ? '#/signup' : '#/signin'
    case 'settings':
      return '#/settings'
    default:
      if (route.folderId === '__unsorted__') return '#/unsorted'
      return route.folderId ? `#/folder/${encodeURIComponent(route.folderId)}` : '#/library'
  }
}

export function navigate(route: Route, replace = false) {
  const hash = hashFor(route)
  if (location.hash === hash) return
  if (replace) history.replaceState(null, '', hash)
  else location.hash = hash
  if (replace) window.dispatchEvent(new HashChangeEvent('hashchange'))
}

export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parseHash(location.hash))
  useEffect(() => {
    const onChange = () => setRoute(parseHash(location.hash))
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])
  return route
}
