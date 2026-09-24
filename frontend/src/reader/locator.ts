/** Phase 0's reader locator: chapterId + blockId + characterOffset. This
 * module computes it from the live DOM rather than from any pagination
 * math, which is what lets the same code serve both Scroll and Paginated
 * modes — a block's on-screen bounding box means the same thing in either
 * layout (CSS columns still lay out as ordinary boxes; only the outer
 * container's overflow/transform differs), so no per-mode branching is
 * needed here.
 *
 * `characterOffset` is a **documented approximation**, not an exact text
 * offset: it's the block's plain-text length scaled by how far the
 * reading anchor line falls through the block's own bounding box. That's
 * precise enough to resume "roughly here" on reload or mode switch; it is
 * not precise enough to anchor a quote or a search result, which would
 * need a real DOM Range/Selection measurement — deliberately deferred,
 * per the approved Phase 2C architecture note on this.
 */

const TAG_RE = /<[^>]+>/g;

export function stripTags(html: string): string {
  return html.replace(TAG_RE, "");
}

export interface AnchorBlock {
  element: HTMLElement;
  blockId: string;
  chapterId: string;
}

function toAnchorBlock(el: HTMLElement): AnchorBlock | null {
  const blockId = el.dataset.blockId;
  const chapterId = el.dataset.chapterId;
  if (!blockId || !chapterId) return null;
  return { element: el, blockId, chapterId };
}

/** Scroll mode: picks the block whose top edge is the last one at/above
 * `anchorY` (i.e. the topmost block currently "under" the reading line),
 * falling back to the very first block — covers the very start of the
 * document, where nothing has scrolled past the anchor line yet. */
export function pickAnchorBlockByScroll(container: HTMLElement, anchorY: number): AnchorBlock | null {
  const elements = Array.from(container.querySelectorAll<HTMLElement>("[data-block-id]"));
  if (elements.length === 0) return null;

  let candidate = elements[0];
  for (const el of elements) {
    if (el.getBoundingClientRect().top <= anchorY) {
      candidate = el;
    } else {
      break;
    }
  }
  return toAnchorBlock(candidate);
}

/** Paginated mode: content isn't natively scrolled (the page "turn" is a
 * transform, not a scroll offset), so the analogous concept isn't a
 * vertical reading line but "the first block visible on the current,
 * column-clipped page" — the first block whose right edge has entered the
 * container's visible bounds. */
export function pickAnchorBlockByPage(container: HTMLElement): AnchorBlock | null {
  const elements = Array.from(container.querySelectorAll<HTMLElement>("[data-block-id]"));
  if (elements.length === 0) return null;

  // The visible page begins at the container's padded edge, not its outer
  // edge: the previous page's blocks end exactly at the padded edge, so
  // measuring from the outer edge matched them too. The 1px margin absorbs
  // sub-pixel rounding at that shared boundary.
  const pageLeft = container.getBoundingClientRect().left + parseFloat(getComputedStyle(container).paddingLeft);
  const candidate = elements.find((el) => el.getBoundingClientRect().right > pageLeft + 1) ?? elements[0];
  return toAnchorBlock(candidate);
}

export function computeApproxCharacterOffset(block: AnchorBlock, anchorY: number): number {
  const rect = block.element.getBoundingClientRect();
  const plainTextLength = stripTags(block.element.innerHTML).length;
  if (plainTextLength === 0 || rect.height === 0) return 0;

  const fraction = Math.min(1, Math.max(0, (anchorY - rect.top) / rect.height));
  return Math.round(fraction * plainTextLength);
}

export function findBlockElement(container: HTMLElement, blockId: string): HTMLElement | null {
  return container.querySelector<HTMLElement>(`[data-block-id="${CSS.escape(blockId)}"]`);
}

/** Jump target lookup for the TOC: both a ReaderSection and a ReaderBlock
 * render with their own id as the real DOM `id` (see Section.tsx and
 * RenderBlock.tsx), so a nav item's `section_id` resolves the same way a
 * block id does — no separate "is this a section or a block" branching
 * needed at the call site. */
export function findElementById(container: HTMLElement, id: string): HTMLElement | null {
  return container.querySelector<HTMLElement>(`#${CSS.escape(id)}`);
}
