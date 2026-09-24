import type { PointerEvent as ReactPointerEvent } from "react";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ReaderChrome } from "./ReaderChrome";
import { ReaderNav } from "./ReaderNav";
import { ReaderSettingsPanel } from "./ReaderSettingsPanel";
import { Section } from "./Section";
import {
  computeApproxCharacterOffset,
  findElementById,
  pickAnchorBlockByPage,
  pickAnchorBlockByScroll,
} from "./locator";
import { readerPreferencesToCssVars } from "./preferences";
import type { ReaderPreferences, ReaderViewMode } from "./types";
import { useReaderArtifact } from "./useReaderArtifact";
import { useReaderPreferences } from "./useReaderPreferences";
import { useReaderProgress } from "./useReaderProgress";

// Fixed distance from the viewport's top edge that counts as "the reading
// line" for locator purposes — arbitrary but stable, so the same point in
// the layout is used consistently for both saving and resuming position.
const ANCHOR_OFFSET_PX = 96;

// The preferences that re-run the paginated layout effect below.
const RELAYOUT_PREFERENCES: (keyof ReaderPreferences)[] = ["fontSize", "lineHeight", "contentWidth", "fontFamily"];

interface ReaderViewProps {
  bookId: string;
}

export function ReaderView({ bookId }: ReaderViewProps) {
  const { artifact, loading, error } = useReaderArtifact(bookId);
  const { initialProgress, loaded: progressLoaded, save } = useReaderProgress(bookId);
  const { preferences, setPreference } = useReaderPreferences();

  const [mode, setMode] = useState<ReaderViewMode>("scroll");
  const [pageIndex, setPageIndex] = useState(0);
  const [pageCount, setPageCount] = useState(1);
  const [pageWidth, setPageWidth] = useState(0);
  const [navOpen, setNavOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);

  const viewportRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const hasResumedRef = useRef(false);
  // Holds either a block id (progress resume, mode switch) or a section id
  // (TOC navigation) — both render with their own id as the real DOM `id`
  // (see locator.ts's findElementById), so one jump path serves both.
  const pendingTargetIdRef = useRef<string | null>(null);
  const [jumpTrigger, setJumpTrigger] = useState(0);
  // Whichever element had focus right before a drawer opened, so closing
  // it (Escape, the × button, or a backdrop click) returns focus there
  // instead of dropping it back to <body>.
  const lastFocusedRef = useRef<HTMLElement | null>(null);
  // Anchor block read just before a relayout-triggering preference change
  // was applied — see changePreference.
  const relayoutAnchorIdRef = useRef<string | null>(null);

  const requestJump = useCallback((targetId: string, newMode?: ReaderViewMode) => {
    pendingTargetIdRef.current = targetId;
    if (newMode) setMode(newMode);
    setJumpTrigger((n) => n + 1);
  }, []);

  // Only one drawer at a time — two overlapping backdrops/panels would be
  // both a visual and a focus-management mess.
  const toggleNav = useCallback(() => {
    setNavOpen((open) => {
      if (!open) {
        lastFocusedRef.current = document.activeElement as HTMLElement | null;
        setSettingsOpen(false);
      }
      return !open;
    });
  }, []);

  const toggleSettings = useCallback(() => {
    setSettingsOpen((open) => {
      if (!open) {
        lastFocusedRef.current = document.activeElement as HTMLElement | null;
        setNavOpen(false);
      }
      return !open;
    });
  }, []);

  const closeNav = useCallback(() => {
    setNavOpen(false);
    lastFocusedRef.current?.focus();
  }, []);

  const closeSettings = useCallback(() => {
    setSettingsOpen(false);
    lastFocusedRef.current?.focus();
  }, []);

  // A typography change reflows the text in the same render that applies
  // it, before layout() can capture an anchor, so blocks may already have
  // slid across page boundaries by then. Read the anchor here instead,
  // while the page still shows what the reader was looking at.
  const changePreference = useCallback(
    <K extends keyof ReaderPreferences>(key: K, value: ReaderPreferences[K]) => {
      const viewport = viewportRef.current;
      if (mode === "paginated" && viewport && RELAYOUT_PREFERENCES.includes(key) && preferences[key] !== value) {
        relayoutAnchorIdRef.current = pickAnchorBlockByPage(viewport)?.blockId ?? null;
      }
      setPreference(key, value);
    },
    [mode, preferences, setPreference],
  );

  const handleNavigate = useCallback(
    (sectionId: string) => {
      requestJump(sectionId);
      closeNav();
    },
    [requestJump, closeNav],
  );

  // Keyboard navigation: arrow/paging keys move through the book, Escape
  // closes whichever drawer is open. Skipped while focus is on a form
  // control so it doesn't fight the browser's own key handling there (e.g.
  // arrow keys moving between the settings panel's radio options).
  useEffect(() => {
    function isFormControlFocused(): boolean {
      const el = document.activeElement as HTMLElement | null;
      if (!el) return false;
      return (
        el.isContentEditable ||
        ["INPUT", "TEXTAREA", "SELECT", "BUTTON"].includes(el.tagName)
      );
    }

    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        if (navOpen) closeNav();
        else if (settingsOpen) closeSettings();
        return;
      }
      if (isFormControlFocused()) return;

      if (mode === "paginated") {
        if (e.key === "ArrowRight" || e.key === "PageDown" || e.key === " ") {
          e.preventDefault();
          setPageIndex((i) => Math.min(pageCount - 1, i + 1));
        } else if (e.key === "ArrowLeft" || e.key === "PageUp") {
          e.preventDefault();
          setPageIndex((i) => Math.max(0, i - 1));
        } else if (e.key === "Home") {
          e.preventDefault();
          setPageIndex(0);
        } else if (e.key === "End") {
          e.preventDefault();
          setPageIndex(pageCount - 1);
        }
      } else {
        const viewport = viewportRef.current;
        if (!viewport) return;
        if (e.key === "ArrowDown" || e.key === "PageDown" || e.key === " ") {
          e.preventDefault();
          viewport.scrollBy({ top: viewport.clientHeight * 0.9, behavior: "smooth" });
        } else if (e.key === "ArrowUp" || e.key === "PageUp") {
          e.preventDefault();
          viewport.scrollBy({ top: -viewport.clientHeight * 0.9, behavior: "smooth" });
        } else if (e.key === "Home") {
          e.preventDefault();
          viewport.scrollTo({ top: 0, behavior: "smooth" });
        } else if (e.key === "End") {
          e.preventDefault();
          viewport.scrollTo({ top: viewport.scrollHeight, behavior: "smooth" });
        }
      }
    }

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [mode, pageCount, navOpen, settingsOpen, closeNav, closeSettings]);

  // Resume: once the artifact and any saved progress are both loaded,
  // switch to the saved mode (if any) and queue a jump to the saved block.
  useEffect(() => {
    if (!artifact || !progressLoaded || hasResumedRef.current) return;
    hasResumedRef.current = true;
    if (initialProgress) {
      requestJump(initialProgress.block_id, initialProgress.mode);
    }
  }, [artifact, progressLoaded, initialProgress, requestJump]);

  // Lays out the paginated column box, and keeps it in sync with the
  // viewport's own size via ResizeObserver. Deliberately always re-reads
  // `viewport.clientWidth/clientHeight` fresh at the moment of layout
  // rather than trusting a separately-stored `pageWidth` state value as
  // an input — React 18 StrictMode's dev-only double-invoke of this
  // effect was observed to leave that state briefly holding a stale
  // reading from a transient in-between layout, which desynced the
  // column math from the real page size. `pageWidth` state still exists
  // as an *output* of this effect (for the transform/jump calculations
  // elsewhere), just never as an input to itself; page height has no
  // other consumer, so it stays a local here rather than state.
  //
  // The layout itself is a two-pass measure: first lay the columns out in
  // a box exactly one page wide and count the columns that overflow it
  // (see layout() below), then set the real column box to `pageCount`
  // columns wide (column-width alone doesn't grow a block's width to fit N
  // columns — width:auto/100% just pins it to one column, which was an
  // earlier bug here: the next page's content bled through at the container
  // edge). Both passes run in one layout call so the measuring pass is
  // never painted, and are applied imperatively via the ref rather
  // than React's `style` prop so a bail-out re-render (pageCount
  // unchanged) can't silently leave the DOM in the measuring state —
  // only `transform` (in the JSX) is React-managed, since it changes on
  // every page turn and never needs remeasuring.
  //
  // `viewport.clientWidth` was observed to read a transient, wrong value
  // (sometimes 0, sometimes some other too-narrow number) for a moment
  // right after the mode-class swap that first applies
  // `.reader__viewport--paginated`'s `max-width` — a real timing race
  // between React's commit and the browser settling that CSS, reproduced
  // even one animation frame later. Rather than guess how many frames are
  // enough, `settleWidth` below polls across frames until it reads the
  // *same* clientWidth twice in a row (capped, so a genuinely-still-0
  // element — e.g. a hidden tab — can't spin forever), which is correct
  // regardless of how many unsettled frames precede it.
  useEffect(() => {
    const viewport = viewportRef.current;
    const content = contentRef.current;
    if (!viewport || !content) return;

    if (mode !== "paginated") {
      content.style.width = "";
      content.style.height = "";
      content.style.columnWidth = "";
      content.style.columnGap = "";
      content.style.removeProperty("--reader-page-height");
      setPageWidth(0);
      return;
    }

    let cancelled = false;
    let frame: number | null = null;

    // viewport carries the page's padding (see reader.css); the content
    // box itself must stay padding-free (a multi-column box with its own
    // padding was observed to stop honoring column-width for text
    // wrapping entirely), so the page's available size is the viewport's
    // own box *minus* that padding, not its raw clientWidth/clientHeight.
    const availableSize = (): { width: number; height: number } => {
      const cs = getComputedStyle(viewport);
      const paddingX = parseFloat(cs.paddingLeft) + parseFloat(cs.paddingRight);
      const paddingY = parseFloat(cs.paddingTop) + parseFloat(cs.paddingBottom);
      return {
        width: viewport.clientWidth - paddingX,
        height: viewport.clientHeight - paddingY,
      };
    };

    const settleWidth = (previous: number | null, attemptsLeft: number) => {
      if (cancelled) return;
      const current = availableSize().width;
      if (current > 0 && current === previous) {
        layout();
        return;
      }
      if (attemptsLeft <= 0) {
        layout();
        return;
      }
      frame = requestAnimationFrame(() => settleWidth(current, attemptsLeft - 1));
    };

    const layout = () => {
      const { width, height } = availableSize();
      if (width === 0 || height === 0) return;

      // Preserve the reader's semantic position across a relayout —
      // resize, orientation change, or a typography/width preference
      // change all land here (see this effect's dependency array) and all
      // change the column geometry under whatever page was showing.
      // Capture which block was on-screen *before* that geometry changes,
      // using the same pickAnchorBlockByPage this file already uses for
      // Scroll<->Paginated mode switching — read here, before any style
      // mutation below, while the DOM still reflects the *previous*
      // layout. A typography change has already reflowed the text by now,
      // so for those the anchor was read before the change was applied
      // (changePreference). Skipped when a jump is already queued (entering
      // Paginated mode via switchMode or a progress resume already knows
      // exactly which block to land on; capturing a second, competing
      // anchor here would race it against a DOM that isn't columnized yet).
      const preservedAnchorId =
        pendingTargetIdRef.current === null
          ? (relayoutAnchorIdRef.current ?? pickAnchorBlockByPage(viewport)?.blockId ?? null)
          : null;
      relayoutAnchorIdRef.current = null;

      // Exposed so reader.css can cap a figure's image to one page's
      // height (see .reader-figure img) — `break-inside: avoid` alone
      // pushes an oversized figure to the next column but doesn't stop it
      // overflowing that column too if the image itself is taller than a
      // page. Set before counting, since it changes how much fits per page.
      content.style.setProperty("--reader-page-height", `${height}px`);

      // Count the columns the browser actually produces rather than
      // estimating from the content's single-column height: break-inside /
      // break-after: avoid move whole blocks to the next column, leaving
      // gaps that a single-column height doesn't include, so that estimate
      // runs short. In a one-page-wide box every column past the first
      // overflows it, and scrollWidth spans all of them.
      content.style.width = `${width}px`;
      content.style.height = `${height}px`;
      content.style.columnWidth = `${width}px`;
      content.style.columnGap = "0px";
      const count = Math.max(1, Math.round(content.scrollWidth / width));
      content.style.width = `${width * count}px`;

      setPageWidth(width);
      setPageCount(count);
      // Resolving the preserved anchor to its new page reuses the exact
      // same requestJump -> pendingTargetIdRef -> jump `useLayoutEffect`
      // path TOC navigation and progress resume already go through — not
      // a second copy of the offsetLeft/pageWidth math. Falls back to a
      // plain clamp only when there was nothing to preserve (empty
      // content, or a jump already in flight handles it instead).
      if (preservedAnchorId) {
        requestJump(preservedAnchorId);
      } else {
        setPageIndex((i) => Math.min(i, count - 1));
      }
    };

    frame = requestAnimationFrame(() => settleWidth(null, 10));
    const observer = new ResizeObserver(layout);
    observer.observe(viewport);
    return () => {
      cancelled = true;
      if (frame !== null) cancelAnimationFrame(frame);
      observer.disconnect();
    };
    // Typography preferences are dependencies, not just `mode`/`artifact`:
    // the ResizeObserver above only fires when the *viewport* box resizes,
    // but changing font size/line height/content width/font family
    // reflows the *content*'s natural height without the viewport itself
    // changing size at all — without these, switching font size while
    // already in Paginated mode left pageCount/pageWidth stale against
    // the new layout.
  }, [
    mode,
    artifact,
    preferences.fontSize,
    preferences.lineHeight,
    preferences.contentWidth,
    preferences.fontFamily,
    requestJump,
  ]);

  // Perform any queued jump (from resume, or from a manual mode switch)
  // once the target mode's layout has painted.
  useLayoutEffect(() => {
    const targetId = pendingTargetIdRef.current;
    if (!targetId) return;

    const content = contentRef.current;
    const viewport = viewportRef.current;
    if (!content || !viewport) return;

    // Resolve only against geometry that matches the mode: Paginated needs
    // layout() to have measured a page, Scroll needs the columns removed
    // (which is when pageWidth goes back to 0). Until then the target stays
    // queued — this effect re-runs when pageWidth changes.
    if ((mode === "paginated") !== (pageWidth > 0)) return;
    pendingTargetIdRef.current = null;

    if (mode === "scroll") {
      findElementById(content, targetId)?.scrollIntoView({ block: "start" });
    } else {
      const el = findElementById(content, targetId);
      if (el) {
        setPageIndex(Math.floor(el.offsetLeft / pageWidth));
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jumpTrigger, mode, pageWidth]);

  // Track reading position: scroll mode listens for scroll, paginated
  // mode re-anchors whenever the visible page changes. Both funnel into
  // the same approximate-offset math (see reader/locator.ts).
  useEffect(() => {
    if (!artifact) return;
    const viewport = viewportRef.current;
    const content = contentRef.current;
    if (!viewport || !content) return;

    const commit = () => {
      const anchorY = viewport.getBoundingClientRect().top + ANCHOR_OFFSET_PX;
      const anchor =
        mode === "scroll" ? pickAnchorBlockByScroll(content, anchorY) : pickAnchorBlockByPage(viewport);
      if (!anchor) return;
      const characterOffset = computeApproxCharacterOffset(anchor, anchorY);
      save({ chapter_id: anchor.chapterId, block_id: anchor.blockId, character_offset: characterOffset, mode });
    };

    if (mode === "paginated") {
      commit();
      return;
    }

    let frame: number | null = null;
    const onScroll = () => {
      if (frame !== null) return;
      frame = requestAnimationFrame(() => {
        frame = null;
        commit();
      });
    };
    viewport.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      viewport.removeEventListener("scroll", onScroll);
      if (frame !== null) cancelAnimationFrame(frame);
    };
    // pageIndex is a dependency so a page turn re-anchors immediately.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [artifact, mode, pageIndex, save]);

  // Swipe-to-turn-page (touch and mouse, via Pointer Events) — Paginated
  // mode only, since Scroll mode already has its own native gesture
  // (scrolling). A tap has near-zero deltaX and never crosses the
  // threshold, so it still reaches whatever was actually tapped inside
  // the content (links, footnotes) without this intercepting it.
  const pointerStartRef = useRef<{ x: number; y: number } | null>(null);
  const SWIPE_THRESHOLD_PX = 50;

  function handlePointerDown(e: ReactPointerEvent) {
    if (mode !== "paginated") return;
    pointerStartRef.current = { x: e.clientX, y: e.clientY };
  }

  function handlePointerUp(e: ReactPointerEvent) {
    const start = pointerStartRef.current;
    pointerStartRef.current = null;
    if (mode !== "paginated" || !start) return;

    const deltaX = e.clientX - start.x;
    const deltaY = e.clientY - start.y;
    if (Math.abs(deltaX) < SWIPE_THRESHOLD_PX || Math.abs(deltaX) < Math.abs(deltaY)) return;

    if (deltaX < 0) {
      setPageIndex((i) => Math.min(pageCount - 1, i + 1));
    } else {
      setPageIndex((i) => Math.max(0, i - 1));
    }
  }

  function switchMode(next: ReaderViewMode) {
    if (next === mode) return;
    const viewport = viewportRef.current;
    const content = contentRef.current;
    if (viewport && content) {
      const anchorY = viewport.getBoundingClientRect().top + ANCHOR_OFFSET_PX;
      const anchor =
        mode === "scroll" ? pickAnchorBlockByScroll(content, anchorY) : pickAnchorBlockByPage(viewport);
      if (anchor) {
        requestJump(anchor.blockId, next);
        return;
      }
    }
    setMode(next);
  }

  if (loading) return <div className="reader reader--status">Loading…</div>;
  if (error || !artifact) {
    return (
      <div className="reader reader--status">
        <p>This book isn't ready to read yet.</p>
        <Link to="/">Back to your library</Link>
      </div>
    );
  }

  return (
    <div className="reader" data-reader-theme={preferences.theme} style={readerPreferencesToCssVars(preferences)}>
      <a href="#reader-content" className="reader__skip-link">
        Skip to content
      </a>
      <ReaderChrome
        title={artifact.meta.title ?? "Untitled"}
        mode={mode}
        onSwitchMode={switchMode}
        navOpen={navOpen}
        onToggleNav={toggleNav}
        settingsOpen={settingsOpen}
        onToggleSettings={toggleSettings}
        hasNavigation={artifact.navigation.length > 0}
      />

      <ReaderNav navigation={artifact.navigation} open={navOpen} onClose={closeNav} onNavigate={handleNavigate} />
      <ReaderSettingsPanel
        open={settingsOpen}
        onClose={closeSettings}
        preferences={preferences}
        setPreference={changePreference}
      />

      <div
        ref={viewportRef}
        className={`reader__viewport reader__viewport--${mode}`}
        onPointerDown={handlePointerDown}
        onPointerUp={handlePointerUp}
        onPointerCancel={() => (pointerStartRef.current = null)}
      >
        <div
          ref={contentRef}
          id="reader-content"
          className="reader__content"
          style={mode === "paginated" ? { transform: `translateX(-${pageIndex * pageWidth}px)` } : undefined}
        >
          {artifact.sections.map((section) => (
            <Section key={section.id} section={section} bookId={bookId} chapterId={section.id} />
          ))}
        </div>
      </div>

      {mode === "paginated" && (
        <footer className="reader__pager">
          <button type="button" disabled={pageIndex === 0} onClick={() => setPageIndex((i) => Math.max(0, i - 1))}>
            ‹ Prev
          </button>
          <span aria-live="polite">
            Page {pageIndex + 1} of {pageCount} · {Math.round(((pageIndex + 1) / pageCount) * 100)}%
          </span>
          <button
            type="button"
            disabled={pageIndex >= pageCount - 1}
            onClick={() => setPageIndex((i) => Math.min(pageCount - 1, i + 1))}
          >
            Next ›
          </button>
        </footer>
      )}
    </div>
  );
}
