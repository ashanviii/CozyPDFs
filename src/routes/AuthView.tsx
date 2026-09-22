import { useState, type FormEvent } from 'react'
import { Mark } from '../components/Icon'
import { useAuth } from '../state/auth'
import { navigate } from '../lib/router'

export function AuthView({ mode }: { mode: 'login' | 'signup' }) {
  const { signIn, signUp } = useAuth()
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const isSignup = mode === 'signup'

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (busy) return
    setError('')
    setBusy(true)
    try {
      if (isSignup) await signUp(name, email, password)
      else await signIn(email, password)
      navigate({ name: 'library', folderId: null })
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Something went wrong.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="auth">
      <div className="auth__card">
        <div className="auth__brand">
          <Mark size={30} />
          cozypdf
        </div>
        <p className="auth__lede">
          {isSignup
            ? 'An account keeps your folders, highlights and reading positions in step across devices.'
            : 'Welcome back. Your library is waiting.'}
        </p>

        <form className="auth__form" onSubmit={submit} noValidate>
          {isSignup && (
            <div className="field">
              <label className="field__label" htmlFor="auth-name">
                Name
              </label>
              <input
                id="auth-name"
                className="input"
                autoComplete="name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="What should we call you?"
              />
            </div>
          )}

          <div className="field">
            <label className="field__label" htmlFor="auth-email">
              Email
            </label>
            <input
              id="auth-email"
              className="input"
              type="email"
              inputMode="email"
              autoComplete="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="you@example.com"
            />
          </div>

          <div className="field">
            <label className="field__label" htmlFor="auth-password">
              Password
            </label>
            <input
              id="auth-password"
              className="input"
              type="password"
              autoComplete={isSignup ? 'new-password' : 'current-password'}
              required
              minLength={8}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder={isSignup ? 'At least 8 characters' : 'Your password'}
            />
          </div>

          {error && <div className="auth__error">{error}</div>}

          <button type="submit" className="btn btn--primary btn--block" disabled={busy}>
            {busy ? <span className="spinner" /> : null}
            {isSignup ? 'Create account' : 'Sign in'}
          </button>

          <div className="auth__alt">
            {isSignup ? 'Already have an account? ' : 'New here? '}
            <a
              href={isSignup ? '#/signin' : '#/signup'}
              onClick={() => {
                setError('')
              }}
            >
              {isSignup ? 'Sign in' : 'Create one'}
            </a>
          </div>
        </form>

        <p className="auth__note">
          You don&apos;t need an account to read.{' '}
          <a href="#/library">Use cozypdf on this device</a> — your books stay in this browser, and
          your PDFs never leave it either way.
        </p>
      </div>
    </div>
  )
}
