import type { User } from './types'

const TOKEN_KEY = 'cozypdf.token'

export const getToken = () => {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export const setToken = (token: string | null) => {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    /* private mode; the session simply will not persist */
  }
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken()
  let response: Response
  try {
    response = await fetch(`/api${path}`, {
      ...init,
      headers: {
        ...(init.body ? { 'content-type': 'application/json' } : {}),
        ...(token ? { authorization: `Bearer ${token}` } : {}),
        ...init.headers,
      },
    })
  } catch {
    throw new ApiError('You appear to be offline. Everything is still saved on this device.', 0)
  }

  if (response.status === 204) return undefined as T
  const text = await response.text()
  let data: unknown = null
  try {
    data = text ? JSON.parse(text) : null
  } catch {
    data = null
  }

  if (!response.ok) {
    const message =
      (data as { error?: string } | null)?.error ??
      (response.status === 404 ? 'Sync server not found.' : 'Something went wrong.')
    throw new ApiError(message, response.status)
  }
  return data as T
}

export const api = {
  signup: (body: { email: string; password: string; name: string }) =>
    request<{ token: string; user: User }>('/auth/signup', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  login: (body: { email: string; password: string }) =>
    request<{ token: string; user: User }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  me: () => request<{ user: User }>('/auth/me'),

  pull: (since: number) =>
    request<{
      now: number
      folders: unknown[]
      books: unknown[]
      annotations: unknown[]
      progress: unknown[]
    }>(`/sync?since=${since}`),

  push: (payload: unknown) =>
    request<{ now: number; applied: number; skipped: number }>('/sync', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  deleteAccount: () => request<{ ok: boolean }>('/account', { method: 'DELETE' }),

  health: () => request<{ ok: boolean }>('/health'),
}
