import { useEffect, useRef, useState } from 'react'
import { openDocument, renderPage, type PdfDoc } from '../../lib/pdf'

/**
 * Fallback for PDFs with no text layer (scans and photographed books). There is
 * nothing to reflow, so we show the pages themselves — lazily, one canvas at a
 * time — rather than pretending the book is empty.
 */
export function ScannedView({
  data,
  onPage,
  scrollRef,
  zoom = 1,
}: {
  data: ArrayBuffer
  onPage: (page: number, total: number) => void
  scrollRef: React.RefObject<HTMLDivElement>
  /** 1 = fit width, up to 3 = 300% — pinch-zoomed in from the reader. */
  zoom?: number
}) {
  const [pdf, setPdf] = useState<PdfDoc | null>(null)
  const [count, setCount] = useState(0)
  const [ratio, setRatio] = useState(1.414)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    let cancelled = false
    let doc: PdfDoc | null = null
    void (async () => {
      doc = await openDocument(data)
      if (cancelled) {
        void doc.destroy()
        return
      }
      const first = await doc.getPage(1)
      const viewport = first.getViewport({ scale: 1 })
      setRatio(viewport.height / viewport.width)
      first.cleanup()
      setCount(doc.numPages)
      setPdf(doc)
    })()
    return () => {
      cancelled = true
      void doc?.destroy()
    }
  }, [data])

  // Render what is on screen; release canvases that scroll away.
  useEffect(() => {
    const container = containerRef.current
    const root = scrollRef.current
    if (!pdf || !container || !root) return

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          const slot = entry.target as HTMLElement
          const number = Number(slot.dataset.page)
          const canvas = slot.querySelector('canvas')
          if (!canvas) continue
          if (entry.isIntersecting) {
            if (!canvas.dataset.rendered) {
              canvas.dataset.rendered = '1'
              void renderPage(pdf, number, canvas, Math.min(900, slot.clientWidth)).catch(() => {
                delete canvas.dataset.rendered
              })
            }
            if (entry.intersectionRatio > 0.5) onPage(number, pdf.numPages)
          } else if (canvas.dataset.rendered) {
            // Free the bitmap; it will be redrawn when it comes back.
            canvas.width = 0
            canvas.height = 0
            delete canvas.dataset.rendered
          }
        }
      },
      { root, rootMargin: '600px 0px', threshold: [0, 0.5] },
    )

    container.querySelectorAll('[data-page]').forEach((slot) => observer.observe(slot))
    return () => observer.disconnect()
  }, [pdf, count, onPage, scrollRef])

  return (
    <div className="pages-zoom-wrap" style={{ overflowX: zoom > 1.01 ? 'auto' : 'hidden' }}>
      <div className="pages" ref={containerRef} style={{ width: `${zoom * 100}%`, minWidth: '100%' }}>
        <p className="pages__note">
          This PDF is a scan — there is no text layer to reflow, so cozypdf shows the original pages.
          Reading settings and Listen Mode need selectable text.
        </p>
        {Array.from({ length: count }, (_, index) => (
          <div
            key={index}
            data-page={index + 1}
            style={{ width: '100%', maxWidth: 900 * zoom, aspectRatio: `1 / ${ratio}` }}
          >
            <canvas style={{ width: '100%' }} />
          </div>
        ))}
        {!count && <span className="spinner" />}
      </div>
    </div>
  )
}
