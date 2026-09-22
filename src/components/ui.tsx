import {
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { Icon } from './Icon'

/* ---------------------------------------------------------------- sheet -- */

interface SheetProps {
  open: boolean
  onClose: () => void
  title?: ReactNode
  variant?: 'center' | 'side'
  children: ReactNode
  footer?: ReactNode
  headExtra?: ReactNode
  labelledBy?: string
}

export function Sheet({
  open,
  onClose,
  title,
  variant = 'center',
  children,
  footer,
  headExtra,
}: SheetProps) {
  const ref = useRef<HTMLDivElement>(null)
  const restoreTo = useRef<HTMLElement | null>(null)
  const titleId = useId()

  useEffect(() => {
    if (!open) return
    restoreTo.current = document.activeElement as HTMLElement | null
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.stopPropagation()
        onClose()
        return
      }
      if (event.key !== 'Tab' || !ref.current) return
      const focusable = ref.current.querySelectorAll<HTMLElement>(
        'a[href],button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),[tabindex]:not([tabindex="-1"])',
      )
      if (!focusable.length) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }
    document.addEventListener('keydown', onKey, true)
    const overflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey, true)
      document.body.style.overflow = overflow
      restoreTo.current?.focus?.()
    }
  }, [open, onClose])

  useLayoutEffect(() => {
    if (!open) return
    const target = ref.current?.querySelector<HTMLElement>(
      'input:not([type="range"]),button:not(.sheet__close),[tabindex]:not([tabindex="-1"])',
    )
    target?.focus({ preventScroll: true })
  }, [open])

  if (!open) return null

  return (
    <>
      <div className="scrim" onClick={onClose} />
      <div
        className={`sheet sheet--${variant}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? titleId : undefined}
        ref={ref}
      >
        {(title || headExtra) && (
          <div className="sheet__head">
            {title && (
              <h2 className="sheet__title" id={titleId}>
                {title}
              </h2>
            )}
            {headExtra}
            <button type="button" className="icon-btn sheet__close" onClick={onClose} aria-label="Close">
              <Icon name="x" size={18} />
            </button>
          </div>
        )}
        {children}
        {footer && <div className="sheet__foot">{footer}</div>}
      </div>
    </>
  )
}

/* ----------------------------------------------------------------- menu -- */

export interface MenuItem {
  label: string
  icon?: Parameters<typeof Icon>[0]['name']
  danger?: boolean
  run: () => void
}

export function Menu({
  x,
  y,
  items,
  onClose,
}: {
  x: number
  y: number
  items: (MenuItem | 'separator')[]
  onClose: () => void
}) {
  const ref = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState({ left: x, top: y })

  useLayoutEffect(() => {
    const element = ref.current
    if (!element) return
    const rect = element.getBoundingClientRect()
    const left = Math.min(x, window.innerWidth - rect.width - 10)
    const top = Math.min(y, window.innerHeight - rect.height - 10)
    setPos({ left: Math.max(10, left), top: Math.max(10, top) })
    element.querySelector<HTMLElement>('button')?.focus({ preventScroll: true })
  }, [x, y])

  useEffect(() => {
    const onDown = (event: MouseEvent) => {
      if (!ref.current?.contains(event.target as Node)) onClose()
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    window.addEventListener('resize', onClose)
    window.addEventListener('scroll', onClose, true)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
      window.removeEventListener('resize', onClose)
      window.removeEventListener('scroll', onClose, true)
    }
  }, [onClose])

  return (
    <div className="menu" style={pos} ref={ref} role="menu">
      {items.map((item, index) =>
        item === 'separator' ? (
          <div className="menu__sep" key={`sep-${index}`} />
        ) : (
          <button
            type="button"
            role="menuitem"
            key={item.label}
            className={`menu__item${item.danger ? ' menu__item--danger' : ''}`}
            onClick={() => {
              onClose()
              item.run()
            }}
          >
            {item.icon && <Icon name={item.icon} size={16} />}
            {item.label}
          </button>
        ),
      )}
    </div>
  )
}

/** Tracks the anchor for a context menu. */
export function useMenu() {
  const [anchor, setAnchor] = useState<{ x: number; y: number } | null>(null)
  const openAt = (event: { clientX: number; clientY: number }) =>
    setAnchor({ x: event.clientX, y: event.clientY })
  const openFrom = (element: HTMLElement) => {
    const rect = element.getBoundingClientRect()
    setAnchor({ x: rect.left, y: rect.bottom + 6 })
  }
  return { anchor, openAt, openFrom, close: () => setAnchor(null) }
}

/* ------------------------------------------------------------- controls -- */

export function Switch({
  checked,
  onChange,
  label,
  hint,
}: {
  checked: boolean
  onChange: (value: boolean) => void
  label: ReactNode
  hint?: ReactNode
}) {
  return (
    <button
      type="button"
      className="switch"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
    >
      <span>
        <span className="row__label">{label}</span>
        {hint && <span className="row__hint" style={{ display: 'block' }}>{hint}</span>}
      </span>
      <span className="switch__track">
        <span className="switch__thumb" />
      </span>
    </button>
  )
}

export function Segmented<T extends string>({
  value,
  options,
  onChange,
  ariaLabel,
}: {
  value: T
  options: { value: T; label: ReactNode }[]
  onChange: (value: T) => void
  ariaLabel?: string
}) {
  return (
    <div className="segmented" role="group" aria-label={ariaLabel}>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          aria-pressed={value === option.value}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}

export function Range({
  label,
  value,
  min,
  max,
  step = 1,
  onChange,
  format,
}: {
  label: string
  value: number
  min: number
  max: number
  step?: number
  onChange: (value: number) => void
  format?: (value: number) => string
}) {
  const id = useId()
  return (
    <div className="tune__group">
      <label className="tune__label" htmlFor={id}>
        <span>{label}</span>
        <span className="tune__value">{format ? format(value) : value}</span>
      </label>
      <input
        id={id}
        className="slider"
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </div>
  )
}

/* --------------------------------------------------------------- dialog -- */

export function Confirm({
  open,
  title,
  body,
  confirmLabel = 'Delete',
  danger = true,
  onConfirm,
  onClose,
}: {
  open: boolean
  title: string
  body: ReactNode
  confirmLabel?: string
  danger?: boolean
  onConfirm: () => void
  onClose: () => void
}) {
  return (
    <Sheet
      open={open}
      onClose={onClose}
      title={title}
      footer={
        <>
          <button type="button" className="btn btn--ghost" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className={`btn ${danger ? 'btn--danger' : 'btn--primary'}`}
            onClick={() => {
              onConfirm()
              onClose()
            }}
          >
            {confirmLabel}
          </button>
        </>
      }
    >
      <div className="sheet__body" style={{ paddingBottom: 6 }}>
        <p style={{ margin: 0, color: 'var(--ink-soft)', lineHeight: 1.6 }}>{body}</p>
      </div>
    </Sheet>
  )
}
