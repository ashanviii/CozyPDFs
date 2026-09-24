import { useEffect, useRef } from "react";
import type { NavigationItem } from "./types";

interface ReaderNavProps {
  navigation: NavigationItem[];
  open: boolean;
  onClose: () => void;
  onNavigate: (sectionId: string) => void;
}

function NavList({ items, onNavigate }: { items: NavigationItem[]; onNavigate: (sectionId: string) => void }) {
  return (
    <ul className="reader-nav__list">
      {items.map((item) => (
        <li key={item.section_id}>
          <button type="button" className="reader-nav__item" onClick={() => onNavigate(item.section_id)}>
            {item.title}
          </button>
          {item.children.length > 0 && <NavList items={item.children} onNavigate={onNavigate} />}
        </li>
      ))}
    </ul>
  );
}

/** Table of contents drawer, built from ReaderArtifact.navigation — a tree
 * Phase 2B already produces from DIR's heading levels (see
 * reader_artifact/build.py's `_build_navigation`) but that no UI has
 * rendered until now. Jumping reuses ReaderView's existing requestJump:
 * a NavigationItem's `section_id` resolves to a real element the same way
 * a block id does (see locator.ts's findElementById). */
export function ReaderNav({ navigation, open, onClose, onNavigate }: ReaderNavProps) {
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
      <nav className="reader-drawer reader-drawer--nav" aria-label="Table of contents">
        <div className="reader-drawer__header">
          <p className="reader-drawer__title">Contents</p>
          <button
            ref={closeButtonRef}
            type="button"
            className="reader-drawer__close"
            aria-label="Close table of contents"
            onClick={onClose}
          >
            ×
          </button>
        </div>
        <NavList items={navigation} onNavigate={onNavigate} />
      </nav>
    </>
  );
}
