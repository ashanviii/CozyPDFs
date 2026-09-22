import { useRef } from 'react'
import { Icon, Mark } from './Icon'
import { Menu, useMenu } from './ui'
import { useAuth } from '../state/auth'
import { navigate } from '../lib/router'
import { useInstallPrompt } from '../lib/pwa'
import { formatRelative } from '../lib/util'

interface TopBarProps {
  query?: string
  onQuery?: (value: string) => void
  onAdd?: () => void
}

export function TopBar({ query, onQuery, onAdd }: TopBarProps) {
  const { user, status, syncState, lastSync, sync, signOut } = useAuth()
  const menu = useMenu()
  const accountRef = useRef<HTMLButtonElement>(null)
  const install = useInstallPrompt()

  const signedIn = status === 'signed-in' && user

  const syncLabel =
    syncState === 'syncing'
      ? 'Syncing'
      : syncState === 'offline'
        ? 'Offline'
        : syncState === 'error'
          ? 'Sync issue'
          : `Synced ${formatRelative(lastSync)}`

  return (
    <header className="topbar">
      <a className="brand" href="#/library" aria-label="cozypdf home">
        <Mark className="brand__mark" size={26} />
        <span>cozypdf</span>
      </a>

      {onQuery ? (
        <div className="search">
          <Icon name="search" size={16} className="search__icon" />
          <input
            className="input"
            type="search"
            value={query}
            placeholder="Search your library"
            aria-label="Search your library"
            onChange={(event) => onQuery(event.target.value)}
          />
        </div>
      ) : (
        <div className="topbar__spacer" />
      )}

      <div className="topbar__spacer" />

      {signedIn && (
        <button
          type="button"
          className={`sync-pill sync-pill--${syncState}`}
          onClick={() => void sync(false)}
          title={syncLabel}
        >
          {syncState === 'syncing' ? (
            <span className="spinner" style={{ width: 11, height: 11, borderWidth: 1.5 }} />
          ) : (
            <span className="sync-pill__dot" />
          )}
          <span>{syncLabel}</span>
        </button>
      )}

      {onAdd && (
        <button type="button" className="btn btn--primary btn--sm" onClick={onAdd}>
          <Icon name="plus" size={16} />
          Add PDF
        </button>
      )}

      <button
        type="button"
        className="icon-btn"
        ref={accountRef}
        aria-label="Account and settings"
        onClick={() => accountRef.current && menu.openFrom(accountRef.current)}
      >
        {signedIn ? (
          <span className="avatar">{(user.name || user.email).slice(0, 1).toUpperCase()}</span>
        ) : (
          <Icon name="user" size={19} />
        )}
      </button>

      {menu.anchor && (
        <Menu
          x={menu.anchor.x}
          y={menu.anchor.y}
          onClose={menu.close}
          items={[
            ...(signedIn
              ? [
                  { label: user.email, icon: 'user' as const, run: () => navigate({ name: 'settings' }) },
                  { label: 'Sync now', icon: 'refresh' as const, run: () => void sync(false) },
                  'separator' as const,
                ]
              : [
                  { label: 'Sign in', icon: 'user' as const, run: () => navigate({ name: 'auth', mode: 'login' }) },
                  {
                    label: 'Create account',
                    icon: 'cloud' as const,
                    run: () => navigate({ name: 'auth', mode: 'signup' }),
                  },
                  'separator' as const,
                ]),
            ...(install.available
              ? [{ label: 'Install cozypdf', icon: 'install' as const, run: () => void install.install() }]
              : []),
            { label: 'Settings', icon: 'sliders', run: () => navigate({ name: 'settings' }) },
            ...(signedIn
              ? ([
                  'separator' as const,
                  { label: 'Sign out', icon: 'logOut' as const, run: () => void signOut() },
                ] as const)
              : []),
          ]}
        />
      )}
    </header>
  )
}
