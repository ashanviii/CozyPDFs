// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { pickAnchorBlockByPage } from "./locator";

// jsdom does no layout, so each block's on-screen box is stubbed. The
// numbers mirror a real Paginated measurement: viewport outer left 320.4,
// 32px left padding (2rem), 560px pages — so the visible page's content
// starts at 352.4, which is also exactly where the previous page's
// blocks end once translateX has shifted them off to the left.
const VIEWPORT_LEFT = 320.4;
const PADDING_LEFT = 32;
const PAGE_WIDTH = 560;
const PAGE_START = VIEWPORT_LEFT + PADDING_LEFT;

function rect(left: number, width: number): DOMRect {
  return { left, right: left + width, width, top: 0, bottom: 100, height: 100, x: left, y: 0, toJSON: () => ({}) };
}

/** `pages[i]` lists the block ids laid out in column i. */
function buildViewport(pages: string[][], currentPage: number): HTMLElement {
  const viewport = document.createElement("div");
  viewport.style.paddingLeft = `${PADDING_LEFT}px`;
  viewport.getBoundingClientRect = () => rect(VIEWPORT_LEFT, 800);

  pages.forEach((ids, pageIndex) => {
    const left = PAGE_START + (pageIndex - currentPage) * PAGE_WIDTH;
    for (const id of ids) {
      const block = document.createElement("div");
      block.dataset.blockId = id;
      block.dataset.chapterId = "ch0";
      block.getBoundingClientRect = () => rect(left, PAGE_WIDTH);
      viewport.appendChild(block);
    }
  });

  document.body.appendChild(viewport);
  return viewport;
}

afterEach(() => {
  document.body.innerHTML = "";
});

describe("pickAnchorBlockByPage", () => {
  it("picks the first block of page 1", () => {
    const viewport = buildViewport([["b1", "b3"], ["b4"]], 0);
    expect(pickAnchorBlockByPage(viewport)?.blockId).toBe("b1");
  });

  it("picks the block on page 2, not the first block of the previous page", () => {
    const viewport = buildViewport([["b1", "b3"], ["b4"]], 1);
    expect(pickAnchorBlockByPage(viewport)?.blockId).toBe("b4");
  });

  it("picks the first block of page 3 when several pages precede it", () => {
    const viewport = buildViewport([["b1"], ["b3"], ["b4", "b5"], ["b6"]], 2);
    expect(pickAnchorBlockByPage(viewport)?.blockId).toBe("b4");
  });

  it("ignores sub-pixel overlap from the previous page's edge", () => {
    const viewport = buildViewport([["b1"], ["b4"]], 1);
    const previous = viewport.querySelector<HTMLElement>('[data-block-id="b1"]')!;
    previous.getBoundingClientRect = () => rect(PAGE_START - PAGE_WIDTH + 0.02, PAGE_WIDTH);
    expect(pickAnchorBlockByPage(viewport)?.blockId).toBe("b4");
  });
});
