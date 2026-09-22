import { useEffect, useState } from 'react'
import { TopBar } from '../components/TopBar'
import { Icon } from '../components/Icon'
import { Confirm, Segmented, Switch } from '../components/ui'
import { useAuth } from '../state/auth'
import { useSettings } from '../state/settings'
import { useLibrary } from '../state/library'
import { useToast } from '../state/toast'
import { estimateUsage, requestPersistence } from '../lib/db'
import { api } from '../lib/api'
import { useInstallPrompt, isStandalone } from '../lib/pwa'
import { formatBytes, formatRelative, plural } from '../lib/util'
import { navigate } from '../lib/router'

export function SettingsView() {
  const { user, status, lastSync, syncState, syncMessage, sync, signOut } = useAuth()
  const { settings, set } = useSettings()
  const { books, folders } = useLibrary()
  const toast = useToast()
  const install = useInstallPrompt()

  const [usage, setUsage] = useState<{ usage: number; quota: number } | null>(null)
  const [persisted, setPersisted] = useState<boolean | null>(null)
  const [clearing, setClearing] = useState(false)
  const [deletingAccount, setDeletingAccount] = useState(false)

  useEffect(() => {
    void estimateUsage().then(setUsage)
    void navigator.storage?.persisted?.().then(setPersisted)
  }, [])

  const signedIn = status === 'signed-in' && user

  return (
    <div className="shell">
      <TopBar />
      <div className="main">
        <div className="page">
          <h1 className="page__title">Settings</h1>

          <section className="card">
            <h2>Account</h2>
            {signedIn ? (
              <>
                <div className="row">
                  <div>
                    <div className="row__label">{user.name}</div>
                    <div className="row__hint">{user.email}</div>
                  </div>
                  <button type="button" className="btn btn--outline btn--sm" onClick={() => void signOut()}>
                    Sign out
                  </button>
                </div>
                <div className="row">
                  <div>
                    <div className="row__label">Sync</div>
                    <div className="row__hint">
                      {syncMessage || `Last synced ${formatRelative(lastSync)}.`} Folders,
                      highlights, notes and positions only — your PDFs never leave this device.
                    </div>
                  </div>
                  <button
                    type="button"
                    className="btn btn--outline btn--sm"
                    disabled={syncState === 'syncing'}
                    onClick={() => void sync(false)}
                  >
                    {syncState === 'syncing' ? <span className="spinner" /> : <Icon name="refresh" size={15} />}
                    Sync now
                  </button>
                </div>
              </>
            ) : (
              <div className="row">
                <div>
                  <div className="row__label">You are reading locally</div>
                  <div className="row__hint">
                    Everything works without an account. Sign in to keep your library in step across
                    devices.
                  </div>
                </div>
                <button
                  type="button"
                  className="btn btn--primary btn--sm"
                  onClick={() => navigate({ name: 'auth', mode: 'login' })}
                >
                  Sign in
                </button>
              </div>
            )}
          </section>

          <section className="card">
            <h2>This device</h2>
            <div className="row">
              <div>
                <div className="row__label">
                  {plural(books.length, 'book')} in {plural(folders.length, 'folder')}
                </div>
                {usage && (
                  <>
                    <div className="row__hint">
                      {formatBytes(usage.usage)} used
                      {usage.quota ? ` of about ${formatBytes(usage.quota)} available` : ''}
                    </div>
                    <div className="meter" style={{ width: 200 }}>
                      <i
                        style={{
                          width: `${Math.min(100, (usage.usage / Math.max(1, usage.quota)) * 100)}%`,
                        }}
                      />
                    </div>
                  </>
                )}
              </div>
            </div>
            <div className="row">
              <div>
                <div className="row__label">Keep my library safe from cleanup</div>
                <div className="row__hint">
                  {persisted
                    ? 'Granted — your browser will not evict cozypdf to reclaim space.'
                    : 'Ask the browser not to delete your books when storage runs low.'}
                </div>
              </div>
              {!persisted && (
                <button
                  type="button"
                  className="btn btn--outline btn--sm"
                  onClick={() =>
                    void requestPersistence().then((ok) => {
                      setPersisted(ok)
                      toast(
                        ok ? 'Your library is now protected.' : 'Your browser declined for now.',
                        ok ? 'success' : 'warn',
                      )
                    })
                  }
                >
                  Request
                </button>
              )}
            </div>
          </section>

          <section className="card">
            <h2>Reading defaults</h2>
            <div className="row">
              <div>
                <div className="row__label">Theme</div>
                <div className="row__hint">Also changeable while reading.</div>
              </div>
              <div style={{ width: 240 }}>
                <Segmented
                  ariaLabel="Theme"
                  value={settings.theme}
                  onChange={(value) => set('theme', value)}
                  options={[
                    { value: 'light', label: 'Light' },
                    { value: 'sepia', label: 'Sepia' },
                    { value: 'dark', label: 'Dark' },
                    { value: 'system', label: 'Auto' },
                  ]}
                />
              </div>
            </div>
            <div className="row" style={{ display: 'block' }}>
              <Switch
                checked={settings.keepAwake}
                onChange={(value) => set('keepAwake', value)}
                label="Keep the screen on while listening"
                hint="Uses the wake lock where the browser supports it."
              />
            </div>
            <div className="row" style={{ display: 'block' }}>
              <Switch
                checked={settings.reduceMotion}
                onChange={(value) => set('reduceMotion', value)}
                label="Reduce motion"
                hint="Turns off page transitions and panel animations."
              />
            </div>
          </section>

          <section className="card">
            <h2>App</h2>
            <div className="row">
              <div>
                <div className="row__label">Install cozypdf</div>
                <div className="row__hint">
                  {isStandalone()
                    ? 'Already installed — you are using the app window.'
                    : install.available
                      ? 'Adds it to your home screen or dock and opens offline.'
                      : 'Use your browser menu: “Install app” or “Add to Home Screen”.'}
                </div>
              </div>
              {install.available && (
                <button
                  type="button"
                  className="btn btn--outline btn--sm"
                  onClick={() => void install.install()}
                >
                  <Icon name="install" size={15} />
                  Install
                </button>
              )}
            </div>
            <div className="row">
              <div>
                <div className="row__label">Offline</div>
                <div className="row__hint">
                  Your books, notes and the app itself are stored on this device, so cozypdf opens
                  with no connection at all.
                </div>
              </div>
            </div>
          </section>

          <section className="card">
            <h2>Danger zone</h2>
            <div className="row">
              <div>
                <div className="row__label">Clear this device</div>
                <div className="row__hint">
                  Removes every book, note and setting stored in this browser.
                  {signedIn ? ' Anything synced stays in your account.' : ' This cannot be undone.'}
                </div>
              </div>
              <button type="button" className="btn btn--danger btn--sm" onClick={() => setClearing(true)}>
                Clear
              </button>
            </div>
            {signedIn && (
              <div className="row">
                <div>
                  <div className="row__label">Delete account</div>
                  <div className="row__hint">
                    Deletes your account and everything synced to it, permanently.
                  </div>
                </div>
                <button
                  type="button"
                  className="btn btn--danger btn--sm"
                  onClick={() => setDeletingAccount(true)}
                >
                  Delete
                </button>
              </div>
            )}
          </section>
        </div>
      </div>

      <Confirm
        open={clearing}
        title="Clear this device?"
        body="Every book, highlight, note and reading position stored in this browser will be removed. Your original PDF files are untouched."
        confirmLabel="Clear everything"
        onConfirm={() => {
          void signOut({ clearDevice: true }).then(() => {
            toast('This device has been cleared.', 'info')
            navigate({ name: 'library', folderId: null })
          })
        }}
        onClose={() => setClearing(false)}
      />

      <Confirm
        open={deletingAccount}
        title="Delete your account?"
        body="Your account and everything synced to it will be deleted permanently. Books on this device stay here."
        confirmLabel="Delete account"
        onConfirm={() => {
          void api
            .deleteAccount()
            .then(() => signOut())
            .then(() => toast('Your account has been deleted.', 'info'))
            .catch(() => toast('Could not reach the server. Nothing was deleted.', 'error'))
        }}
        onClose={() => setDeletingAccount(false)}
      />
    </div>
  )
}
