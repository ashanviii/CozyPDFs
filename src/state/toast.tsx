import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from 'react'

type Tone = 'info' | 'success' | 'warn' | 'error'

interface Toast {
  id: number
  message: string
  tone: Tone
  action?: { label: string; run: () => void }
}

interface ToastContextValue {
  toast: (message: string, tone?: Tone, action?: Toast['action']) => void
}

const ToastContext = createContext<ToastContextValue | null>(null)

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const nextId = useRef(1)

  const dismiss = useCallback((id: number) => {
    setToasts((current) => current.filter((t) => t.id !== id))
  }, [])

  const toast = useCallback(
    (message: string, tone: Tone = 'info', action?: Toast['action']) => {
      const id = nextId.current++
      setToasts((current) => [...current.slice(-3), { id, message, tone, action }])
      window.setTimeout(() => dismiss(id), tone === 'error' ? 7000 : 4200)
    },
    [dismiss],
  )

  const value = useMemo(() => ({ toast }), [toast])

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {toasts.map((item) => (
          <div key={item.id} className={`toast toast--${item.tone}`}>
            <span>{item.message}</span>
            {item.action && (
              <button
                type="button"
                className="toast__action"
                onClick={() => {
                  item.action?.run()
                  dismiss(item.id)
                }}
              >
                {item.action.label}
              </button>
            )}
            <button
              type="button"
              className="toast__close"
              aria-label="Dismiss"
              onClick={() => dismiss(item.id)}
            >
              ×
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  const context = useContext(ToastContext)
  if (!context) throw new Error('useToast must be used inside ToastProvider')
  return context.toast
}
