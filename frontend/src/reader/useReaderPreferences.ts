import { useCallback, useEffect, useState } from "react";
import { DEFAULT_READER_PREFERENCES, READER_PREFERENCES_STORAGE_KEY } from "./preferences";
import type { ReaderPreferences } from "./types";

function loadPreferences(): ReaderPreferences {
  try {
    const raw = localStorage.getItem(READER_PREFERENCES_STORAGE_KEY);
    if (!raw) return DEFAULT_READER_PREFERENCES;
    // Spread over the defaults, not just the parsed value, so a
    // preferences shape from an older build (missing a since-added key)
    // still fills in every field rather than rendering with `undefined`.
    return { ...DEFAULT_READER_PREFERENCES, ...JSON.parse(raw) };
  } catch {
    return DEFAULT_READER_PREFERENCES;
  }
}

/** Reader-wide display preferences, persisted to localStorage only — see
 * the note on ReaderPreferences in types.ts for why this never touches the
 * backend's per-book ReadingProgress. */
export function useReaderPreferences() {
  const [preferences, setPreferences] = useState<ReaderPreferences>(loadPreferences);

  useEffect(() => {
    try {
      localStorage.setItem(READER_PREFERENCES_STORAGE_KEY, JSON.stringify(preferences));
    } catch {
      // Private-browsing storage blocks, quota errors, etc. — losing the
      // save isn't worth surfacing to the reader mid-read.
    }
  }, [preferences]);

  const setPreference = useCallback(
    <K extends keyof ReaderPreferences>(key: K, value: ReaderPreferences[K]) => {
      setPreferences((prev) => ({ ...prev, [key]: value }));
    },
    [],
  );

  return { preferences, setPreference };
}
