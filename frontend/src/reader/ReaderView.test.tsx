// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ReaderArtifact, ReadingProgress } from "./types";

const mocks = vi.hoisted(() => ({
  progress: null as ReadingProgress | null,
  artifact: null as ReaderArtifact | null,
}));

vi.mock("../lib/api", () => ({
  assetUrl: () => "",
  api: {
    getReaderArtifact: () => Promise.resolve(mocks.artifact!),
    getProgress: () => (mocks.progress ? Promise.resolve(mocks.progress) : Promise.reject(new Error("404"))),
    saveProgress: () => Promise.resolve(),
  },
}));

import { ReaderView } from "./ReaderView";

const block = (id: string, order: number) => ({
  id,
  type: "paragraph" as const,
  order,
  content: `<p>${id}</p>`,
  level: null,
  preserve_as_image: false,
  asset_id: null,
  caption: null,
  confidence: 1,
  source_page: 1,
});

function artifactOf(ids: string[]): ReaderArtifact {
  return {
    schema_version: 1,
    book_id: "book-1",
    dir_schema_version: 1,
    meta: { title: "Test", author: null, language: null, source_type: "pdf" },
    sections: [{ id: "ch0", title: "Chapter", level: 1, blocks: ids.map(block), children: [] }],
    assets: [],
    navigation: [{ section_id: "ch0", title: "Chapter", level: 1, children: [] }],
  };
}

// --- jsdom has no layout engine; model just enough of one. ------------
// Viewport: 624x587 with 32px padding -> a 560x523 page. Each block is
// either fixed-height (a figure) or `lines` of text whose height follows
// the *rendered* --reader-font-size / --reader-line-height, so a typography
// change reflows the text immediately, inside whatever columns are still
// applied — just as a browser does before layout() gets to re-measure.
// Once columnized, blocks are packed into columns of the content's current
// height and never split, so a block that doesn't fit the rest of a column
// starts the next one (break-inside: avoid). Before columnizing (Scroll
// mode, or Paginated before layout() has run) every block is at offsetLeft
// 0 — which is why resolving a jump against missing or stale geometry
// lands on the wrong page.
type ModelItem = { fixed: number } | { lines: number };
let model: Record<string, ModelItem>;
const PADDING = 32;
const SCROLL_TOP: Record<string, number> = { b1: -500, b3: -200, b4: 50 };

// Default fixture: heading + b1 + b3 fill page 1, b4 starts page 2.
const DEFAULT_IDS = ["b1", "b3", "b4"];
const DEFAULT_MODEL: Record<string, ModelItem> = { heading: { fixed: 60 }, b1: { fixed: 250 }, b3: { lines: 6 }, b4: { fixed: 250 } };

function contentOf(el: Element): HTMLElement | null {
  return el.closest<HTMLElement>(".reader__content");
}
function isColumnized(content: HTMLElement | null): boolean {
  return !!content?.style.columnWidth;
}
function translateX(content: HTMLElement): number {
  return parseFloat(content.style.transform.replace("translateX(", "")) || 0;
}
function itemHeight(id: string): number {
  const item = model[id];
  if ("fixed" in item) return item.fixed;
  const style = document.querySelector<HTMLElement>(".reader")!.style;
  const fontPx = parseFloat(style.getPropertyValue("--reader-font-size")) * 16;
  return item.lines * fontPx * parseFloat(style.getPropertyValue("--reader-line-height"));
}
function flowIds(): string[] {
  return ["heading", ...[...document.querySelectorAll<HTMLElement>("[data-block-id]")].map((el) => el.dataset.blockId!)];
}
/** Column index of every item at the given column height, plus the total. */
function pack(columnHeight: number): { columnOf: Record<string, number>; columns: number } {
  const columnOf: Record<string, number> = {};
  let column = 0;
  let used = 0;
  for (const id of flowIds()) {
    const h = itemHeight(id);
    if (used > 0 && used + h > columnHeight) {
      column += 1;
      used = 0;
    }
    columnOf[id] = column;
    used += h;
  }
  return { columnOf, columns: column + 1 };
}
function columnWidthOf(content: HTMLElement): number {
  return parseFloat(content.style.columnWidth);
}
function blockOffset(el: HTMLElement): number {
  const content = contentOf(el);
  if (!isColumnized(content)) return 0;
  return pack(parseFloat(content!.style.height)).columnOf[el.dataset.blockId!] * columnWidthOf(content!);
}
function domRect(left: number, top: number, width: number, height: number): DOMRect {
  return { left, top, width, height, right: left + width, bottom: top + height, x: left, y: top, toJSON: () => ({}) };
}

let scrollCalls: Array<{ id: string; columnized: boolean }> = [];

const resizeObservers = new Set<{ cb: ResizeObserverCallback }>();
function triggerResize() {
  for (const o of [...resizeObservers]) o.cb([], {} as ResizeObserver);
}

let restorers: Array<() => void> = [];
function stubGetter(proto: object, prop: string, get: (this: HTMLElement) => number) {
  const original = Object.getOwnPropertyDescriptor(proto, prop);
  Object.defineProperty(proto, prop, { configurable: true, get });
  restorers.push(() => (original ? Object.defineProperty(proto, prop, original) : delete (proto as Record<string, unknown>)[prop]));
}

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  localStorage.clear();
  mocks.progress = null;
  mocks.artifact = artifactOf(DEFAULT_IDS);
  model = DEFAULT_MODEL;
  scrollCalls = [];

  const style = document.createElement("style");
  style.textContent = `.reader__viewport { padding: ${PADDING}px; }`;
  document.head.appendChild(style);

  // requestAnimationFrame never fires here, so layout() runs only when a
  // test explicitly delivers a resize — i.e. pageWidth stays 0 until then.
  vi.stubGlobal("requestAnimationFrame", () => 1);
  vi.stubGlobal("cancelAnimationFrame", () => {});
  vi.stubGlobal("CSS", { escape: (value: string) => value });
  vi.stubGlobal(
    "ResizeObserver",
    class {
      entry: { cb: ResizeObserverCallback };
      constructor(cb: ResizeObserverCallback) {
        this.entry = { cb };
      }
      observe() {
        resizeObservers.add(this.entry);
      }
      disconnect() {
        resizeObservers.delete(this.entry);
      }
      unobserve() {}
    },
  );

  const proto = HTMLElement.prototype;
  stubGetter(proto, "clientWidth", function () {
    return this.classList.contains("reader__viewport") ? 624 : 0;
  });
  stubGetter(proto, "clientHeight", function () {
    return this.classList.contains("reader__viewport") ? 587 : 0;
  });
  // Single-column height: what an estimate from one unbroken column sees.
  stubGetter(proto, "scrollHeight", function () {
    if (!this.classList.contains("reader__content")) return 0;
    return flowIds().reduce((sum, id) => sum + itemHeight(id), 0);
  });
  // Columns past the box's own width overflow it, and scrollWidth counts them.
  stubGetter(proto, "scrollWidth", function () {
    if (!this.classList.contains("reader__content")) return 0;
    const boxWidth = parseFloat(this.style.width) || 0;
    if (!isColumnized(this)) return boxWidth;
    return Math.max(boxWidth, pack(parseFloat(this.style.height)).columns * columnWidthOf(this));
  });
  stubGetter(proto, "offsetLeft", function () {
    return this.dataset.blockId ? blockOffset(this) : 0;
  });

  const originalRect = proto.getBoundingClientRect;
  proto.getBoundingClientRect = function (this: HTMLElement) {
    const id = this.dataset.blockId;
    if (!id) return domRect(0, 0, 624, 587);
    const content = contentOf(this)!;
    if (!isColumnized(content)) return domRect(PADDING, SCROLL_TOP[id] ?? -1000, 560, 100);
    const width = columnWidthOf(content);
    return domRect(PADDING + blockOffset(this) + translateX(content), 0, width, 100);
  };
  restorers.push(() => (proto.getBoundingClientRect = originalRect));

  const originalScroll = proto.scrollIntoView;
  proto.scrollIntoView = function (this: HTMLElement) {
    scrollCalls.push({ id: this.dataset.blockId ?? this.id, columnized: isColumnized(contentOf(this)) });
  };
  restorers.push(() => (proto.scrollIntoView = originalScroll));

  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  document.body.innerHTML = "";
  document.head.innerHTML = "";
  resizeObservers.clear();
  restorers.forEach((restore) => restore());
  restorers = [];
  vi.unstubAllGlobals();
});

async function flush() {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

async function mount() {
  await act(async () => {
    root.render(
      <MemoryRouter>
        <ReaderView bookId="book-1" />
      </MemoryRouter>,
    );
  });
  await flush();
}

function pagerText(): string | null | undefined {
  return container.querySelector(".reader__pager span")?.textContent;
}

function click(label: string) {
  const button = [...container.querySelectorAll("button")].find((b) => b.textContent === label)!;
  act(() => button.click());
}

function choosePreference(name: string, label: string) {
  if (!container.querySelector(".reader-drawer--settings")) {
    act(() => container.querySelector<HTMLButtonElement>('[aria-label="Display settings"]')!.click());
  }
  const input = [...container.querySelectorAll<HTMLInputElement>(`input[name="${name}"]`)].find(
    (i) => i.labels![0].textContent === label,
  )!;
  act(() => input.click());
}

/** Blocks laid out in the column the current transform shows. */
function visibleBlocks(): string[] {
  const content = container.querySelector<HTMLElement>(".reader__content")!;
  const width = columnWidthOf(content);
  const page = Math.round(-translateX(content) / width);
  return [...content.querySelectorAll<HTMLElement>("[data-block-id]")]
    .filter((el) => Math.round(blockOffset(el) / width) === page)
    .map((el) => el.dataset.blockId!);
}

function resumeAt(blockId: string) {
  mocks.progress = {
    chapter_id: "ch0",
    block_id: blockId,
    character_offset: 0,
    mode: "paginated",
    updated_at: "2026-01-01T00:00:00Z",
  };
}

describe("ReaderView queued jumps", () => {
  it("keeps a jump queued while pageWidth is 0 and resolves it once layout measures a page", async () => {
    await mount();
    click("Paginated");

    // Entered Paginated mode with a jump to b4 queued, but no layout yet.
    expect(pagerText()).toMatch(/^Page 1 of 1/);

    act(() => triggerResize());

    expect(pagerText()).toMatch(/^Page 2 of 2/);
  });

  it("resumes saved Paginated progress once layout completes", async () => {
    mocks.progress = {
      chapter_id: "ch0",
      block_id: "b4",
      character_offset: 0,
      mode: "paginated",
      updated_at: "2026-01-01T00:00:00Z",
    };
    await mount();

    expect(container.querySelector(".reader__viewport--paginated")).not.toBeNull();
    expect(pagerText()).toMatch(/^Page 1 of 1/);

    act(() => triggerResize());

    expect(pagerText()).toMatch(/^Page 2 of 2/);
  });

  it("does not resolve a re-entry jump against the previous Paginated session's page width", async () => {
    await mount();
    click("Paginated");
    act(() => triggerResize());
    expect(pagerText()).toMatch(/^Page 2 of 2/);

    click("Scroll");
    click("Paginated");
    act(() => triggerResize());

    expect(pagerText()).toMatch(/^Page 2 of 2/);
  });

  it("scrolls to the Paginated anchor only after the columns have been removed", async () => {
    await mount();
    click("Paginated");
    act(() => triggerResize());
    expect(pagerText()).toMatch(/^Page 2 of 2/);

    click("Scroll");

    expect(scrollCalls.at(-1)).toEqual({ id: "b4", columnized: false });
  });

  it("resolves a TOC jump in Scroll mode immediately", async () => {
    await mount();
    act(() => container.querySelector<HTMLButtonElement>('[aria-label="Table of contents"]')!.click());
    act(() => container.querySelector<HTMLButtonElement>(".reader-nav__item")!.click());

    expect(scrollCalls.at(-1)).toEqual({ id: "ch0", columnized: false });
  });
});

describe("ReaderView typography relayout", () => {
  // Nine 5-line paragraphs after a 40px heading. At the default 18px/1.7
  // each is 153px: three per 523px page, so b7 opens page 3. Larger type
  // (204px or 180px each) fits only two per page and pushes b7 to page 4 —
  // and, reflowed inside the old columns before layout() re-measures, it
  // would put b5 at the top of page 3.
  const TEXT_IDS = ["b1", "b2", "b3", "b4", "b5", "b6", "b7", "b8", "b9"];

  beforeEach(() => {
    mocks.artifact = artifactOf(TEXT_IDS);
    model = { heading: { fixed: 40 }, ...Object.fromEntries(TEXT_IDS.map((id) => [id, { lines: 5 }])) };
    resumeAt("b7");
  });

  async function openAtB7() {
    await mount();
    act(() => triggerResize());
    expect(pagerText()).toMatch(/^Page 3 of 3 ·/);
    expect(visibleBlocks()[0]).toBe("b7");
  }

  it("keeps the anchor block when a font-size change moves it to a later page", async () => {
    await openAtB7();

    choosePreference("reader-font-size", "X-Large");
    act(() => triggerResize());

    expect(visibleBlocks()[0]).toBe("b7");
    expect(pagerText()).toMatch(/^Page 4 of 5 ·/);
  });

  it("keeps the anchor block when a line-height change moves it to a later page", async () => {
    await openAtB7();

    choosePreference("reader-line-height", "Relaxed");
    act(() => triggerResize());

    expect(visibleBlocks()[0]).toBe("b7");
    expect(pagerText()).toMatch(/^Page 4 of 5 ·/);
  });
});

describe("ReaderView page count", () => {
  it("counts the extra column break-inside: avoid produces (the 'Page 4 of 3' case)", async () => {
    // 60 + 480 + 184 + 480 = 1204px of content, i.e. 2.3 pages by height —
    // but b1 doesn't fit under the heading, b3 doesn't fit under b1, and b4
    // doesn't fit under b3, so each starts a new column: 4 columns.
    mocks.artifact = artifactOf(["b1", "b3", "b4"]);
    model = { heading: { fixed: 60 }, b1: { fixed: 480 }, b3: { lines: 6 }, b4: { fixed: 480 } };
    resumeAt("b4");
    await mount();

    act(() => triggerResize());

    expect(visibleBlocks()).toEqual(["b4"]);
    expect(pagerText()).toMatch(/^Page 4 of 4 ·/);
  });
});
