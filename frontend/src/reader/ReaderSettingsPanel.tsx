import { useEffect, useRef } from "react";
import {
  CONTENT_WIDTH_VALUES,
  FONT_FAMILY_VALUES,
  FONT_SIZE_VALUES,
  LINE_HEIGHT_VALUES,
  READER_THEMES,
} from "./preferences";
import type {
  ReaderContentWidth,
  ReaderFontFamily,
  ReaderFontSize,
  ReaderLineHeight,
  ReaderPreferences,
  ReaderTheme,
} from "./types";

interface ReaderSettingsPanelProps {
  open: boolean;
  onClose: () => void;
  preferences: ReaderPreferences;
  setPreference: <K extends keyof ReaderPreferences>(key: K, value: ReaderPreferences[K]) => void;
}

const THEME_LABELS: Record<ReaderTheme, string> = {
  light: "Light",
  sepia: "Sepia",
  dark: "Dark",
  system: "System",
};

const FONT_FAMILY_LABELS: Record<ReaderFontFamily, string> = {
  serif: "Serif",
  sans: "Sans Serif",
};

const FONT_SIZE_LABELS: Record<ReaderFontSize, string> = {
  small: "Small",
  medium: "Medium",
  large: "Large",
  "x-large": "X-Large",
};

const LINE_HEIGHT_LABELS: Record<ReaderLineHeight, string> = {
  compact: "Compact",
  standard: "Standard",
  relaxed: "Relaxed",
};

const CONTENT_WIDTH_LABELS: Record<ReaderContentWidth, string> = {
  narrow: "Narrow",
  medium: "Medium",
  wide: "Wide",
};

function OptionGroup<T extends string>({
  legend,
  name,
  value,
  options,
  labels,
  onChange,
}: {
  legend: string;
  name: string;
  value: T;
  options: readonly T[];
  labels: Record<T, string>;
  onChange: (value: T) => void;
}) {
  return (
    <fieldset className="reader-settings__group">
      <legend>{legend}</legend>
      <div className="reader-settings__options">
        {options.map((option) => {
          const id = `${name}-${option}`;
          return (
            <span key={option} className="reader-settings__option">
              <input
                type="radio"
                id={id}
                name={name}
                checked={value === option}
                onChange={() => onChange(option)}
              />
              <label htmlFor={id}>{labels[option]}</label>
            </span>
          );
        })}
      </div>
    </fieldset>
  );
}

/** Display-settings drawer: every control here is a direct, labeled
 * read/write view onto useReaderPreferences — no local state of its own,
 * so a change applies (and persists to localStorage) immediately. */
export function ReaderSettingsPanel({ open, onClose, preferences, setPreference }: ReaderSettingsPanelProps) {
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  // Move focus into the drawer as soon as it opens — ReaderView already
  // restores it to whatever triggered the open when `onClose` runs.
  useEffect(() => {
    if (open) closeButtonRef.current?.focus();
  }, [open]);

  if (!open) return null;

  return (
    <>
      <div className="reader-drawer-backdrop" onClick={onClose} />
      <div className="reader-drawer reader-drawer--settings" role="dialog" aria-modal="true" aria-label="Display settings">
        <div className="reader-drawer__header">
          <p className="reader-drawer__title">Display</p>
          <button
            ref={closeButtonRef}
            type="button"
            className="reader-drawer__close"
            aria-label="Close display settings"
            onClick={onClose}
          >
            ×
          </button>
        </div>

        <OptionGroup
          legend="Theme"
          name="reader-theme"
          value={preferences.theme}
          options={READER_THEMES}
          labels={THEME_LABELS}
          onChange={(value) => setPreference("theme", value)}
        />
        <OptionGroup
          legend="Font"
          name="reader-font-family"
          value={preferences.fontFamily}
          options={Object.keys(FONT_FAMILY_VALUES) as ReaderFontFamily[]}
          labels={FONT_FAMILY_LABELS}
          onChange={(value) => setPreference("fontFamily", value)}
        />
        <OptionGroup
          legend="Font size"
          name="reader-font-size"
          value={preferences.fontSize}
          options={Object.keys(FONT_SIZE_VALUES) as ReaderFontSize[]}
          labels={FONT_SIZE_LABELS}
          onChange={(value) => setPreference("fontSize", value)}
        />
        <OptionGroup
          legend="Line spacing"
          name="reader-line-height"
          value={preferences.lineHeight}
          options={Object.keys(LINE_HEIGHT_VALUES) as ReaderLineHeight[]}
          labels={LINE_HEIGHT_LABELS}
          onChange={(value) => setPreference("lineHeight", value)}
        />
        <OptionGroup
          legend="Reading width"
          name="reader-content-width"
          value={preferences.contentWidth}
          options={Object.keys(CONTENT_WIDTH_VALUES) as ReaderContentWidth[]}
          labels={CONTENT_WIDTH_LABELS}
          onChange={(value) => setPreference("contentWidth", value)}
        />
      </div>
    </>
  );
}
