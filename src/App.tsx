import { useCallback, useRef } from 'react'
import { ToastProvider } from './state/toast'
import { SettingsProvider } from './state/settings'
import { AuthProvider } from './state/auth'
import { LibraryProvider, useLibrary } from './state/library'
import { useRoute } from './lib/router'
import { LibraryView } from './routes/LibraryView'
import { ReaderView } from './routes/ReaderView'
import { AuthView } from './routes/AuthView'
import { SettingsView } from './routes/SettingsView'

export default function App() {
  return (
    <SettingsProvider>
      <ToastProvider>
        <LibraryProvider>
          <WithAuth />
        </LibraryProvider>
      </ToastProvider>
    </SettingsProvider>
  )
}

/**
 * Auth sits inside the library so a sync that pulls new records can refresh the
 * shelf, without either store importing the other.
 */
function WithAuth() {
  const { refresh } = useLibrary()
  const refreshRef = useRef(refresh)
  refreshRef.current = refresh
  const onLibraryChange = useCallback(() => {
    void refreshRef.current()
  }, [])

  return (
    <AuthProvider onLibraryChange={onLibraryChange}>
      <Routes />
    </AuthProvider>
  )
}

function Routes() {
  const route = useRoute()

  switch (route.name) {
    case 'reader':
      return <ReaderView bookId={route.bookId} key={route.bookId} />
    case 'auth':
      return <AuthView mode={route.mode} key={route.mode} />
    case 'settings':
      return <SettingsView />
    default:
      return <LibraryView folderId={route.folderId} />
  }
}
