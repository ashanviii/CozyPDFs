/** Reader display preferences: defaults, the discrete steps each control
 * offers, and how a step maps to the CSS custom properties reader.css
 * already exposes (see the `--reader-*` vars there). Kept separate from
 * useReaderPreferences.ts so a future settings panel can import just the
 * value tables without the storage/state logic. */

import type { CSSProperties } from "react";
import type {
  ReaderContentWidth,
  ReaderFontFamily,
  ReaderFontSize,
  ReaderLineHeight,
  ReaderPreferences,
  ReaderTheme,
} from "./types";

export const READER_PREFERENCES_STORAGE_KEY = "cozypdfs:reader-preferences";

export const DEFAULT_READER_PREFERENCES: ReaderPreferences = {
  theme: "light",
  fontFamily: "serif",
  fontSize: "medium",
  lineHeight: "standard",
  contentWidth: "medium",
};

export const READER_THEMES: ReaderTheme[] = ["light", "sepia", "dark", "system"];

export const FONT_FAMILY_VALUES: Record<ReaderFontFamily, string> = {
  serif: 'Georgia, "Times New Roman", serif',
  sans: '-apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif',
};

export const FONT_SIZE_VALUES: Record<ReaderFontSize, string> = {
  small: "1rem",
  medium: "1.125rem",
  large: "1.25rem",
  "x-large": "1.5rem",
};

export const LINE_HEIGHT_VALUES: Record<ReaderLineHeight, string> = {
  compact: "1.4",
  standard: "1.7",
  relaxed: "2",
};

export const CONTENT_WIDTH_VALUES: Record<ReaderContentWidth, string> = {
  narrow: "560px",
  medium: "680px",
  wide: "820px",
};

/** Only the four value-scale controls become inline style overrides —
 * theme is applied as a `data-reader-theme` attribute instead (see
 * ReaderView), since it switches a whole palette via CSS selectors rather
 * than a single custom property. */
export function readerPreferencesToCssVars(preferences: ReaderPreferences): CSSProperties {
  return {
    "--reader-font-family": FONT_FAMILY_VALUES[preferences.fontFamily],
    "--reader-font-size": FONT_SIZE_VALUES[preferences.fontSize],
    "--reader-line-height": LINE_HEIGHT_VALUES[preferences.lineHeight],
    "--reader-content-width": CONTENT_WIDTH_VALUES[preferences.contentWidth],
  } as CSSProperties;
}
