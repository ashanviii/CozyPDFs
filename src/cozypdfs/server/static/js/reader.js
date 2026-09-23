// The reader: wraps epub.js. The EPUB fully controls its own semantic
// structure -- this file controls typography, theme, pagination/scroll,
// and progress, never touching the book's content.

let currentBook = null;
let currentRendition = null;
let currentBookId = null;
let progressSaveTimer = null;
let fontScale = 100;
let lastCfi = null;

const READER_THEMES = {
  light: { body: { background: '#ffffff', color: '#1b1b1b' } },
  warm: { body: { background: '#f6ecd9', color: '#3a2f22' } },
  dark: { body: { background: '#1c1b1a', color: '#e8e2d6' } },
};

// "paginated": click/arrow to turn discrete pages, two-up on wide screens.
// "scrolled": one continuous vertical scroll per chapter -- epub.js's
// documented recipe for a scroll reading mode ("scrolled-doc" flow).
function renditionOptionsFor(mode) {
  if (mode === 'scrolled') {
    return { width: '100%', height: '100%', flow: 'scrolled-doc' };
  }
  return { width: '100%', height: '100%', flow: 'paginated', spread: 'auto' };
}

async function openReader(bookId) {
  currentBookId = bookId;
  closeReaderIfOpen();

  let entry;
  try {
    entry = await API.getBook(bookId);
  } catch (err) {
    navigate('#/library');
    return;
  }

  document.getElementById('reader-book-title').textContent = entry.title;
  document.getElementById('reader-book-author').textContent = entry.author || '';
  document.getElementById('download-epub-link').href = `/api/library/${bookId}/epub`;

  // epub.js guesses the archive vs. unpacked-directory format from the
  // URL's shape (e.g. whether it ends in ".epub"); our URL doesn't, so
  // it must be told explicitly or it tries to fetch container.xml as a
  // sibling path instead of unpacking the fetched binary.
  currentBook = ePub(`/api/library/${bookId}/epub`, { openAs: 'epub' });

  updateModeButtons();
  await createRendition(entry.progress_cfi || undefined);

  currentBook.loaded.navigation.then((nav) => renderToc(nav.toc));
  currentBook.ready
    .then(() => currentBook.locations.generate(1600))
    .catch(() => {});
}

// (Re)creates the rendition using the current reading-mode preference and
// displays at `startLocation` (a CFI, or undefined for the book's start).
async function createRendition(startLocation) {
  const viewer = document.getElementById('viewer');
  viewer.innerHTML = '';

  const mode = loadPref('readingMode', 'paginated');
  currentRendition = currentBook.renderTo(viewer, renditionOptionsFor(mode));

  Object.entries(READER_THEMES).forEach(([name, styles]) =>
    currentRendition.themes.register(name, styles)
  );
  currentRendition.themes.select(loadPref('theme', 'warm'));
  fontScale = loadPref('fontScale', 100);
  currentRendition.themes.fontSize(fontScale + '%');
  updateFontLabel();
  updateThemeSwatches();

  currentRendition.on('relocated', (location) => {
    lastCfi = location.start.cfi;
    let percent = 0;
    if (currentBook.locations && currentBook.locations.length()) {
      percent = Math.round(currentBook.locations.percentageFromCfi(lastCfi) * 100);
    }
    document.getElementById('progress-fill').style.width = percent + '%';
    document.getElementById('progress-label').textContent = percent + '%';
    scheduleProgressSave(lastCfi, percent);
  });

  document.getElementById('prev-btn').onclick = () => currentRendition.prev();
  document.getElementById('next-btn').onclick = () => currentRendition.next();
  window.removeEventListener('keydown', readerKeyHandler);
  window.addEventListener('keydown', readerKeyHandler);

  await currentRendition.display(startLocation);
}

async function setReadingMode(mode) {
  if (!currentBook) return;
  savePref('readingMode', mode);
  updateModeButtons();
  const resumeAt = lastCfi || undefined;
  if (currentRendition) {
    currentRendition.destroy();
    currentRendition = null;
  }
  await createRendition(resumeAt);
}

function updateModeButtons() {
  const current = loadPref('readingMode', 'paginated');
  document.querySelectorAll('.toggle-btn[data-mode]').forEach((btn) => {
    btn.classList.toggle('active', btn.dataset.mode === current);
  });
}

function readerKeyHandler(e) {
  if (document.getElementById('reader-view').hidden) return;
  if (e.key === 'ArrowLeft') currentRendition && currentRendition.prev();
  if (e.key === 'ArrowRight') currentRendition && currentRendition.next();
}

function scheduleProgressSave(cfi, percent) {
  clearTimeout(progressSaveTimer);
  const bookId = currentBookId;
  progressSaveTimer = setTimeout(() => {
    if (bookId) API.updateProgress(bookId, cfi, percent);
  }, 800);
}

function renderToc(toc) {
  const list = document.getElementById('toc-list');
  list.innerHTML = '';
  toc.forEach((item) => {
    const li = document.createElement('li');
    const a = document.createElement('a');
    a.href = '#';
    a.textContent = item.label.trim();
    a.addEventListener('click', (e) => {
      e.preventDefault();
      currentRendition.display(item.href);
      document.getElementById('toc-panel').hidden = true;
    });
    li.appendChild(a);
    list.appendChild(li);
  });
}

function closeReaderIfOpen() {
  window.removeEventListener('keydown', readerKeyHandler);
  document.getElementById('toc-panel').hidden = true;
  document.getElementById('settings-panel').hidden = true;
  if (currentRendition) {
    currentRendition.destroy();
    currentRendition = null;
  }
  currentBook = null;
  currentBookId = null;
  lastCfi = null;
}

function loadPref(key, fallback) {
  try {
    const v = localStorage.getItem('cozypdfs:' + key);
    return v !== null ? JSON.parse(v) : fallback;
  } catch (e) {
    return fallback;
  }
}
function savePref(key, value) {
  try {
    localStorage.setItem('cozypdfs:' + key, JSON.stringify(value));
  } catch (e) {}
}

function updateFontLabel() {
  document.getElementById('font-size-label').textContent = fontScale + '%';
}
function updateThemeSwatches() {
  const current = loadPref('theme', 'warm');
  document.querySelectorAll('.swatch').forEach((btn) => {
    btn.classList.toggle('active', btn.dataset.theme === current);
  });
}

document.getElementById('font-inc').addEventListener('click', () => {
  fontScale = Math.min(180, fontScale + 10);
  currentRendition && currentRendition.themes.fontSize(fontScale + '%');
  updateFontLabel();
  savePref('fontScale', fontScale);
});
document.getElementById('font-dec').addEventListener('click', () => {
  fontScale = Math.max(70, fontScale - 10);
  currentRendition && currentRendition.themes.fontSize(fontScale + '%');
  updateFontLabel();
  savePref('fontScale', fontScale);
});
document.querySelectorAll('.swatch').forEach((btn) => {
  btn.addEventListener('click', () => {
    const theme = btn.dataset.theme;
    currentRendition && currentRendition.themes.select(theme);
    savePref('theme', theme);
    updateThemeSwatches();
  });
});
document.querySelectorAll('.toggle-btn[data-mode]').forEach((btn) => {
  btn.addEventListener('click', () => setReadingMode(btn.dataset.mode));
});

document.getElementById('toc-btn').addEventListener('click', () => {
  document.getElementById('settings-panel').hidden = true;
  const panel = document.getElementById('toc-panel');
  panel.hidden = !panel.hidden;
});
document.getElementById('settings-btn').addEventListener('click', () => {
  document.getElementById('toc-panel').hidden = true;
  const panel = document.getElementById('settings-panel');
  panel.hidden = !panel.hidden;
});
