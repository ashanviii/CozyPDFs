import { Link } from "react-router-dom";
import type { ReaderViewMode } from "./types";

interface ReaderChromeProps {
  title: string;
  mode: ReaderViewMode;
  onSwitchMode: (mode: ReaderViewMode) => void;
  navOpen: boolean;
  onToggleNav: () => void;
  settingsOpen: boolean;
  onToggleSettings: () => void;
  hasNavigation: boolean;
}

/** The reader's top bar. Split out of ReaderView so the drawer-toggle
 * buttons added here (Contents / Aa) don't grow that file's already-large
 * layout/locator logic — this component owns no reading state of its
 * own, just renders what ReaderView passes it. */
export function ReaderChrome({
  title,
  mode,
  onSwitchMode,
  navOpen,
  onToggleNav,
  settingsOpen,
  onToggleSettings,
  hasNavigation,
}: ReaderChromeProps) {
  return (
    <header className="reader__bar">
      <Link to="/" className="reader__back">
        ‹ Library
      </Link>

      {hasNavigation && (
        <button
          type="button"
          className={`reader__chrome-toggle${navOpen ? " is-active" : ""}`}
          aria-pressed={navOpen}
          aria-label="Table of contents"
          onClick={onToggleNav}
        >
          Contents
        </button>
      )}

      <p className="reader__title">{title}</p>

      <div className="reader__mode-toggle" role="group" aria-label="Reading mode">
        <button type="button" className={mode === "scroll" ? "is-active" : ""} onClick={() => onSwitchMode("scroll")}>
          Scroll
        </button>
        <button
          type="button"
          className={mode === "paginated" ? "is-active" : ""}
          onClick={() => onSwitchMode("paginated")}
        >
          Paginated
        </button>
      </div>

      <button
        type="button"
        className={`reader__chrome-toggle${settingsOpen ? " is-active" : ""}`}
        aria-pressed={settingsOpen}
        aria-label="Display settings"
        onClick={onToggleSettings}
      >
        Aa
      </button>
    </header>
  );
}
