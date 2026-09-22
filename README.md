# cozypdf

A calm place to read PDFs. Drop a book in, and cozypdf rebuilds it as flowing
text you can set in any font at any size — then reads it aloud if you'd rather
listen. Everything lives on your device; an account only syncs the small stuff.

- **Book Mode** — reflowable text with the book's own images and links kept
  in place, five typefaces, size / spacing / width / margin controls,
  light · sepia · dark, scroll or paged, search, bookmarks, five-colour
  highlights, notes, chapter navigation, saved position.
- **Listen Mode** — natural system voices, speed and pitch, sentence-by-sentence
  highlighting that follows along, and automatic continuation through chapters.
- **Ambience** — rain, fireplace, café or forest, synthesized live in the
  browser, so they never loop and never need downloading.
- **Local-first PWA** — installable, works with no connection, and your PDFs
  never leave your device even when you're signed in.

## Running it

```bash
npm install
npm run dev
```

That serves the app on <http://localhost:5173> and the optional sync server on
<http://localhost:8787>. The app is fully usable without the server — signing in
is the only thing that needs it.

For a production build:

```bash
npm run build
npm start
```

`npm start` serves the built app and the API together from port 8787
(`PORT`, `COZYPDF_PORT`, or a first argument overrides it).

## How it reads a PDF

A PDF has no paragraphs — only glyphs at coordinates. `src/lib/pdf.ts` rebuilds
the structure:

1. **Lines** — text items are clustered by baseline and joined left to right,
   inserting spaces where the horizontal gap implies one.
2. **Columns** — if lines fall into two bands with a clear gutter, each line is
   given a reading-order *band* so a two-column paper comes out in the right
   order instead of zig-zagging.
3. **Running heads and footers** — text near the top or bottom edge that
   repeats across pages, or that's just a page number, is dropped so it never
   interrupts the reading flow (a footer needs two repeats to go, a header
   three, since short section headings can legitimately recur).
4. **Paragraphs** — lines are stitched back together, breaking on vertical
   gaps, first-line indents, short closing lines, bullets and headings, and
   de-hyphenating words split across a line break. Paragraphs continue across
   page boundaries.
5. **Headings** — detected by size, weight, capitalisation and chapter-ish
   wording, then ranked into three levels.
6. **Links** — every link annotation (an external URL or a jump to another
   page) is mapped onto the exact characters it covers, even though a PDF
   usually hands back a whole sentence as one unbroken run rather than one
   item per word. External links open in a new tab; internal ones jump you to
   that spot in the book.
7. **Images** — every embedded picture's placement is recovered by walking the
   page's drawing commands, then cropped out of a single render of that page
   (so any colour space or compression pdf.js supports just works) and
   dropped into the flow exactly where it appeared, alongside the text around
   it. Overlapping layers — a badge stamped over a background photo — collapse
   into the one that actually matters.
8. **Chapters** — taken from the PDF outline when there is one (resolving each
   destination to a page), otherwise from the detected headings.

**Covers, dividers, and diagram pages are kept as they looked, not reflowed.**
A page whose text is deliberately laid over or beside artwork — a styled
cover, a part-divider, a labelled diagram — can't be pulled apart into plain
paragraphs without losing what made it work. cozypdf recognises that case
(artwork covering most of the page with little real prose, or text lines that
geometrically overlap the art rather than sitting beside it) and renders the
whole page as a single picture instead. An ordinary page — prose with the
occasional captioned figure — is unaffected and reflows as normal.

Scans with no text layer are detected and shown as page images instead, with a
note explaining why the reading controls don't apply.

## What syncs

Signed out, nothing leaves the browser. Signed in, cozypdf exchanges four kinds
of small record — folders, book metadata, annotations and reading positions —
merged last-write-wins on `updatedAt`. Covers and PDF bytes are always local; a
book synced from another device shows as *Not on this device* until you add the
file there, at which point it adopts the existing record rather than duplicating
it.

The server (`server/index.js`) is one file and one dependency (Express). Storage
is Node's built-in SQLite, passwords are scrypt-hashed, and sessions are
HMAC-signed tokens.

## Keyboard

| Key | Action |
| --- | --- |
| `←` `→` / `PgUp` `PgDn` | Turn page or scroll |
| `Space` | Play / pause while listening |
| `c` · `n` · `/` | Contents · Notes · Search |
| `t` | Reading settings |
| `b` | Bookmark |
| `l` | Listen mode |
| `f` | Hide the chrome |
| `Home` `End` | Start / end of book |
| `Esc` | Close a panel, or leave the book |

## Layout

```
src/
  lib/        pdf extraction, storage, tts, ambience, sync, routing
  state/      settings, auth, library, toasts
  components/ shared UI + the reader's flow, panels and listen bar
  routes/     library, reader, auth, settings
  styles/     tokens and three themes
server/       auth + sync (Express, node:sqlite)
scripts/      PWA icon generator (dependency-free PNG encoder)
```

## Notes

- Voices come from the operating system, so the shortlist differs per device.
  cozypdf ranks what it finds and offers the four best, plus the full list.
- Reading position is stored by paragraph index, so it survives changing the
  font, size or layout.
- Storage is IndexedDB. Settings asks the browser to make it persistent so a
  large library isn't evicted under storage pressure.
