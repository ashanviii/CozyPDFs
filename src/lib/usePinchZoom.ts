import { useEffect, useRef } from 'react'

interface PinchHandlers {
  /** Fires once when a second finger touches down, before any onPinch call. */
  onStart?: () => void
  /** Fires on every move of a two-finger gesture with the distance between
   *  the fingers relative to where the gesture started (1 = unchanged). */
  onPinch: (scale: number) => void
  /** Fires once both fingers have lifted. */
  onEnd?: () => void
}

/**
 * Recognises a two-finger pinch that starts on `ref`'s element. Ordinary
 * one-finger touches (scrolling, tapping) are left completely alone — only
 * a genuine second finger is intercepted, and only for the gesture's
 * duration.
 *
 * Listens on `document` rather than the target itself: the target (the
 * reader's scroll container) doesn't exist yet on the render that mounts
 * this hook — it's still showing a loading state — and a plain effect on
 * `ref` has no way to notice the node arriving later, since a ref changing
 * doesn't trigger a re-render. Checking `ref.current` inside the handlers
 * instead, at the moment a touch actually happens, sidesteps that entirely.
 */
export function usePinchZoom(ref: React.RefObject<HTMLElement>, handlers: PinchHandlers) {
  const handlersRef = useRef(handlers)
  handlersRef.current = handlers

  useEffect(() => {
    let startDist = 0
    let pinching = false

    const distance = (touches: TouchList) =>
      Math.hypot(touches[0].clientX - touches[1].clientX, touches[0].clientY - touches[1].clientY)

    const onTouchStart = (e: TouchEvent) => {
      if (e.touches.length !== 2) return
      const el = ref.current
      if (!el || !el.contains(e.target as Node)) return
      startDist = distance(e.touches)
      pinching = startDist > 0
      if (pinching) handlersRef.current.onStart?.()
    }
    const onTouchMove = (e: TouchEvent) => {
      if (!pinching || e.touches.length !== 2) return
      // Stop the page's own pinch-to-zoom / scroll from fighting our own.
      e.preventDefault()
      handlersRef.current.onPinch(distance(e.touches) / startDist)
    }
    const onTouchEnd = (e: TouchEvent) => {
      if (pinching && e.touches.length < 2) {
        pinching = false
        handlersRef.current.onEnd?.()
      }
    }

    document.addEventListener('touchstart', onTouchStart, { passive: true })
    document.addEventListener('touchmove', onTouchMove, { passive: false })
    document.addEventListener('touchend', onTouchEnd, { passive: true })
    document.addEventListener('touchcancel', onTouchEnd, { passive: true })
    return () => {
      document.removeEventListener('touchstart', onTouchStart)
      document.removeEventListener('touchmove', onTouchMove)
      document.removeEventListener('touchend', onTouchEnd)
      document.removeEventListener('touchcancel', onTouchEnd)
    }
  }, [ref])
}
