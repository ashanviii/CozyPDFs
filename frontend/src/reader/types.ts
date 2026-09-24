/** Mirrors backend/src/cozypdfs/reader_artifact/schema.py field-for-field
 * (snake_case as sent over the wire — no case translation happens on
 * either side). Keep these two in sync by hand; there's no shared schema
 * generation yet. */

export type ReaderBlockType =
  | "paragraph"
  | "heading"
  | "list"
  | "quote"
  | "image"
  | "table"
  | "equation"
  | "figure"
  | "footnote";

export interface ReaderAsset {
  id: string;
  filename: string;
  media_type: string;
  width: number | null;
  height: number | null;
  alt_text: string | null;
}

export interface ReaderBlock {
  id: string;
  type: ReaderBlockType;
  order: number;
  content: string;
  level: number | null;
  preserve_as_image: boolean;
  asset_id: string | null;
  caption: string | null;
  confidence: number;
  source_page: number | null;
}

export interface ReaderSection {
  id: string;
  title: string | null;
  level: number;
  blocks: ReaderBlock[];
  children: ReaderSection[];
}

export interface NavigationItem {
  section_id: string;
  title: string;
  level: number;
  children: NavigationItem[];
}

export interface ReaderMeta {
  title: string | null;
  author: string | null;
  language: string | null;
  source_type: string;
}

export interface ReaderArtifact {
  schema_version: number;
  book_id: string;
  dir_schema_version: number;
  meta: ReaderMeta;
  sections: ReaderSection[];
  assets: ReaderAsset[];
  navigation: NavigationItem[];
}

export type ReaderViewMode = "scroll" | "paginated";

/** Display preferences — client-only (localStorage, see preferences.ts),
 * deliberately separate from ReadingProgress: this is how the reader
 * looks, not where the reader is. Never sent to the backend. */
export type ReaderTheme = "light" | "sepia" | "dark" | "system";
export type ReaderFontFamily = "serif" | "sans";
export type ReaderFontSize = "small" | "medium" | "large" | "x-large";
export type ReaderLineHeight = "compact" | "standard" | "relaxed";
export type ReaderContentWidth = "narrow" | "medium" | "wide";

export interface ReaderPreferences {
  theme: ReaderTheme;
  fontFamily: ReaderFontFamily;
  fontSize: ReaderFontSize;
  lineHeight: ReaderLineHeight;
  contentWidth: ReaderContentWidth;
}

export interface ReadingLocator {
  chapter_id: string;
  block_id: string;
  character_offset: number;
  mode: ReaderViewMode;
}

export interface ReadingProgress extends ReadingLocator {
  updated_at: string;
}
