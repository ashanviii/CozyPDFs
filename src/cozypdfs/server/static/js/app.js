// Library view, upload flow, and hash-based routing between "#/library"
// and "#/read/<id>". No framework/build step -- see the project's own
// "simplest correct architecture, don't over-engineer" rule.

const API = {
  async listLibrary() {
    const r = await fetch('/api/library');
    return r.json();
  },
  async getBook(id) {
    const r = await fetch(`/api/library/${id}`);
    if (!r.ok) throw new Error('Book not found');
    return r.json();
  },
  async upload(file) {
    const fd = new FormData();
    fd.append('file', file);
    const r = await fetch('/api/books', { method: 'POST', body: fd });
    if (!r.ok) {
      const err = await r.json().catch(() => ({ detail: 'Upload failed' }));
      throw new Error(err.detail || 'Upload failed');
    }
    return r.json();
  },
  async updateProgress(id, cfi, percent) {
    await fetch(`/api/library/${id}/progress`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ cfi, percent }),
    });
  },
};

const COVER_COLORS = ['#a85a2e', '#6f8a5e', '#4f6f8f', '#8f5170', '#8a6d3b', '#3f7d74'];

function coverColorFor(title) {
  let hash = 0;
  for (const ch of title || '') hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  return COVER_COLORS[hash % COVER_COLORS.length];
}

function escapeHtml(s) {
  const d = document.createElement('div');
  d.textContent = s ?? '';
  return d.innerHTML;
}

function bookCardHTML(entry) {
  const coverUrl = entry.has_cover ? `/api/library/${entry.id}/cover` : null;
  const initial = (entry.title || '?').trim()[0]?.toUpperCase() || '?';
  const color = coverColorFor(entry.title || '');
  const pct = Math.round(entry.progress_percent || 0);
  return `
    <div class="book-card" data-id="${entry.id}">
      <div class="book-cover" style="${coverUrl ? '' : `background:${color}`}">
        ${coverUrl ? `<img src="${coverUrl}" alt="">` : `<span class="cover-initial">${initial}</span>`}
        ${pct > 0 ? `<div class="cover-progress"><div style="width:${pct}%"></div></div>` : ''}
      </div>
      <div class="book-title">${escapeHtml(entry.title)}</div>
      <div class="book-author">${escapeHtml(entry.author || 'Unknown author')}</div>
    </div>`;
}

async function renderLibrary() {
  const grid = document.getElementById('book-grid');
  const empty = document.getElementById('empty-state');
  const entries = await API.listLibrary();
  if (entries.length === 0) {
    grid.innerHTML = '';
    empty.hidden = false;
    return;
  }
  empty.hidden = true;
  grid.innerHTML = entries.map(bookCardHTML).join('');
  grid.querySelectorAll('.book-card').forEach((card) => {
    card.addEventListener('click', () => navigate(`#/read/${card.dataset.id}`));
  });
}

// --- routing ---

function showView(name) {
  document.getElementById('library-view').hidden = name !== 'library';
  document.getElementById('reader-view').hidden = name !== 'reader';
}

function navigate(hash) {
  if (location.hash === hash) route();
  else location.hash = hash;
}

async function route() {
  const hash = location.hash || '#/library';
  const readMatch = hash.match(/^#\/read\/([0-9a-f]{32})$/);
  if (readMatch) {
    showView('reader');
    await openReader(readMatch[1]);
  } else {
    showView('library');
    closeReaderIfOpen();
    await renderLibrary();
  }
}

window.addEventListener('hashchange', route);
document.getElementById('back-btn').addEventListener('click', () => navigate('#/library'));

// --- upload flow ---

const STAGE_LABELS = {
  uploading: 'Uploading…',
  analyze: 'Analyzing your book…',
  layout: 'Reading the page layout…',
  reading_order: 'Determining reading order…',
  artifacts: 'Removing page numbers and running headers…',
  paragraphs: 'Reconstructing paragraphs…',
  structure: 'Reconstructing chapters…',
  epub: 'Building your EPUB…',
  validate: 'Validating your EPUB…',
  done: 'Your book is ready.',
  added: 'Added to your library.',
};

function openUploadModal() {
  document.getElementById('upload-title').textContent = 'Adding your book…';
  document.getElementById('upload-log').innerHTML = '';
  document.getElementById('upload-result').hidden = true;
  document.getElementById('upload-error').hidden = true;
  document.getElementById('upload-modal').hidden = false;
}

function closeUploadModal() {
  document.getElementById('upload-modal').hidden = true;
}

function appendUploadLog(message) {
  const log = document.getElementById('upload-log');
  const li = document.createElement('li');
  li.textContent = message;
  log.appendChild(li);
  log.scrollTop = log.scrollHeight;
}

async function handleFileSelected(file) {
  if (!file) return;
  openUploadModal();
  let job;
  try {
    job = await API.upload(file);
  } catch (err) {
    showUploadError(err.message);
    return;
  }
  const es = new EventSource(`/api/jobs/${job.job_id}/stream`);
  es.onmessage = (evt) => {
    const data = JSON.parse(evt.data);
    appendUploadLog(STAGE_LABELS[data.stage] || data.message);
    if (data.stage === 'added') {
      es.close();
      showUploadSuccess(data.book_id);
    } else if (data.stage === 'error') {
      es.close();
      showUploadError(data.message);
    }
  };
  es.onerror = () => es.close();
}

function showUploadSuccess(bookId) {
  document.getElementById('upload-title').textContent = 'Your book is ready.';
  document.getElementById('upload-result').hidden = false;
  document.getElementById('read-now-btn').onclick = () => {
    closeUploadModal();
    navigate(`#/read/${bookId}`);
  };
  document.getElementById('upload-download-link').href = `/api/library/${bookId}/epub`;
  renderLibrary();
}

function showUploadError(message) {
  document.getElementById('upload-title').textContent = 'Conversion failed';
  const box = document.getElementById('upload-error');
  box.hidden = false;
  box.textContent = message;
}

document.getElementById('add-book-btn').addEventListener('click', () => {
  document.getElementById('file-input').click();
});
document.getElementById('file-input').addEventListener('change', (e) => {
  handleFileSelected(e.target.files[0]);
  e.target.value = '';
});
document.getElementById('upload-close-btn').addEventListener('click', closeUploadModal);

const libMain = document.querySelector('.lib-main');
libMain.addEventListener('dragover', (e) => {
  e.preventDefault();
  libMain.classList.add('drag-over');
});
libMain.addEventListener('dragleave', () => libMain.classList.remove('drag-over'));
libMain.addEventListener('drop', (e) => {
  e.preventDefault();
  libMain.classList.remove('drag-over');
  const file = e.dataTransfer.files[0];
  if (file) handleFileSelected(file);
});

route();
