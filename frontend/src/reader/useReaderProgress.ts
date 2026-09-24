import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import type { ReadingLocator, ReadingProgress } from "./types";

const SAVE_DEBOUNCE_MS = 1500;

/** Loads any previously-saved locator for this book once on mount, and
 * exposes a debounced `save` — called on every locator change while
 * reading, but only actually PUTs after the reader has settled on a
 * position for a moment, so scrolling doesn't fire a request per frame. */
export function useReaderProgress(bookId: string) {
  const [initialProgress, setInitialProgress] = useState<ReadingProgress | null>(null);
  const [loaded, setLoaded] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .getProgress(bookId)
      .then((progress) => {
        if (!cancelled) setInitialProgress(progress);
      })
      .catch(() => {
        // No saved progress yet (404) — start from the top, silently.
      })
      .finally(() => {
        if (!cancelled) setLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, [bookId]);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  const save = useCallback(
    (locator: ReadingLocator) => {
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => {
        api.saveProgress(bookId, locator).catch(() => {
          // Best-effort: losing one autosave tick isn't worth surfacing to
          // the reader mid-read; the next locator change will retry.
        });
      }, SAVE_DEBOUNCE_MS);
    },
    [bookId],
  );

  return { initialProgress, loaded, save };
}
