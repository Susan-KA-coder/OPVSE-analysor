const STORAGE_KEYS = {
  activeTab: 'pb-active-tab',
  author: 'pb-author-name'
};

const BOARD_TABS = ['action', 'safety', 'whereabout', 'good-stories'];
const POLL_INTERVAL_MS = 5000;

const dateEl = document.getElementById('current-date');
const syncStatusEl = document.getElementById('sync-status');
const tabButtons = document.querySelectorAll('.tab-btn');
const tabPanels = document.querySelectorAll('.tab-panel');
const entryForms = Array.from(document.querySelectorAll('.entry-form'));
const entryLists = new Map(Array.from(document.querySelectorAll('[data-entry-list]')).map((listEl) => [listEl.dataset.entryList, listEl]));

const formState = Object.fromEntries(BOARD_TABS.map((tabId) => [tabId, { editingId: null }]));

let boardData = createEmptyBoard();
let lastLoadedAt = null;

if (dateEl) {
  dateEl.textContent = new Date().toLocaleDateString('en-GB', {
    weekday: 'short', day: 'numeric', month: 'long', year: 'numeric'
  });
}

function createEmptyBoard() {
  return { tabs: Object.fromEntries(BOARD_TABS.map((tabId) => [tabId, []])) };
}

function activateTab(tabId) {
  tabButtons.forEach((btn) => btn.classList.toggle('active', btn.dataset.tab === tabId));
  tabPanels.forEach((panel) => panel.classList.toggle('active', panel.id === `tab-${tabId}`));
  localStorage.setItem(STORAGE_KEYS.activeTab, tabId);
}

function setSyncStatus(message, tone = 'neutral') {
  if (!syncStatusEl) return;
  syncStatusEl.textContent = message;
  syncStatusEl.dataset.tone = tone;
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function formatTimestamp(value) {
  const timestamp = new Date(value);
  if (Number.isNaN(timestamp.getTime())) return 'Unknown time';
  return timestamp.toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
}

function setFormStatus(formEl, message, tone = 'neutral') {
  const statusEl = formEl.querySelector('.form-status');
  if (!statusEl) return;
  statusEl.textContent = message;
  statusEl.dataset.tone = tone;
}

function syncAuthorInputs(author) {
  entryForms.forEach((formEl) => {
    const authorInput = formEl.elements.author;
    if (authorInput && authorInput.value !== author) authorInput.value = author;
  });
}

function resetForm(tabId) {
  const formEl = document.querySelector(`[data-tab-form="${tabId}"]`);
  if (!formEl) return;
  const cancelButton = formEl.querySelector('.form-cancel');
  const textArea = formEl.elements.text;
  formState[tabId].editingId = null;
  if (textArea) textArea.value = '';
  if (cancelButton) cancelButton.hidden = true;
  setFormStatus(formEl, '');
}

function beginEdit(tabId, entryId) {
  const formEl = document.querySelector(`[data-tab-form="${tabId}"]`);
  const entry = boardData.tabs[tabId].find((item) => item.id === entryId);
  if (!formEl || !entry) return;
  formState[tabId].editingId = entryId;
  formEl.elements.author.value = entry.author;
  formEl.elements.text.value = entry.text;
  formEl.querySelector('.form-cancel').hidden = false;
  setFormStatus(formEl, 'Editing existing update.', 'neutral');
  formEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function renderEntries(tabId) {
  const listEl = entryLists.get(tabId);
  const entries = boardData.tabs[tabId] || [];
  if (!listEl) return;

  if (!entries.length) {
    listEl.innerHTML = '<div class="empty-state">No updates yet. Add the first one using the form.</div>';
    return;
  }

  listEl.innerHTML = entries.map((entry) => {
    const isEditing = formState[tabId].editingId === entry.id;
    return `
      <article class="entry-card${isEditing ? ' is-editing' : ''}">
        <div class="entry-topline">
          <div>
            <p class="entry-author">${escapeHtml(entry.author)}</p>
            <p class="entry-meta">Updated ${escapeHtml(formatTimestamp(entry.updatedAt))}</p>
          </div>
          <div class="entry-actions">
            <button type="button" class="entry-btn" data-entry-action="edit" data-tab-id="${tabId}" data-entry-id="${entry.id}">Edit</button>
            <button type="button" class="entry-btn danger" data-entry-action="delete" data-tab-id="${tabId}" data-entry-id="${entry.id}">Delete</button>
          </div>
        </div>
        <p class="entry-text">${escapeHtml(entry.text).replace(/\n/g, '<br />')}</p>
      </article>
    `;
  }).join('');
}

function renderBoard() {
  BOARD_TABS.forEach(renderEntries);
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...options
  });

  if (!response.ok) {
    let errorMessage = 'Request failed.';
    try {
      const errorBody = await response.json();
      errorMessage = errorBody.error || errorMessage;
    } catch {}
    throw new Error(errorMessage);
  }

  if (response.status === 204) return null;
  return response.json();
}

async function loadBoard({ silent = false } = {}) {
  try {
    const nextBoard = await requestJson('/api/board');
    boardData = nextBoard;
    lastLoadedAt = new Date();
    renderBoard();

    if (!silent) {
      setSyncStatus('Shared board connected.', 'success');
    } else if (lastLoadedAt) {
      setSyncStatus(`Last synced at ${formatTimestamp(lastLoadedAt.toISOString())}.`, 'neutral');
    }
  } catch (error) {
    setSyncStatus('Server offline. Start the Python app to sync updates.', 'error');
    if (!silent) console.error(error);
  }
}

async function saveEntry(tabId, formEl) {
  const author = formEl.elements.author.value.trim();
  const text = formEl.elements.text.value.trim();
  const editingId = formState[tabId].editingId;

  if (!author || !text) {
    setFormStatus(formEl, 'Name and update are required.', 'error');
    return;
  }

  localStorage.setItem(STORAGE_KEYS.author, author);
  syncAuthorInputs(author);
  setFormStatus(formEl, 'Saving update...', 'neutral');

  try {
    const latest = await requestJson('/api/board');
    const board = latest.tabs || createEmptyBoard().tabs;
    const ts = new Date().toISOString();

    if (editingId) {
      const idx = board[tabId].findIndex((e) => e.id === editingId);
      if (idx !== -1) board[tabId][idx] = { ...board[tabId][idx], author, text, updatedAt: ts };
    } else {
      board[tabId].unshift({ id: crypto.randomUUID(), tab: tabId, author, text, createdAt: ts, updatedAt: ts });
    }

    const res = await requestJson('/api/board', {
      method: 'PUT',
      body: JSON.stringify({ tabs: board })
    });

    boardData = res.tabs ? res : { tabs: board };
    resetForm(tabId);
    renderBoard();
    setSyncStatus(`Last saved at ${formatTimestamp(ts)}.`, 'success');
  } catch (error) {
    setFormStatus(formEl, error.message, 'error');
  }
}

async function deleteEntry(tabId, entryId) {
  if (!window.confirm('Delete this update for everyone?')) return;

  try {
    const latest = await requestJson('/api/board');
    const board = latest.tabs || createEmptyBoard().tabs;
    board[tabId] = board[tabId].filter((e) => e.id !== entryId);
    if (formState[tabId].editingId === entryId) resetForm(tabId);
    const res = await requestJson('/api/board', {
      method: 'PUT',
      body: JSON.stringify({ tabs: board })
    });
    boardData = res.tabs ? res : { tabs: board };
    renderBoard();
  } catch (error) {
    const formEl = document.querySelector(`[data-tab-form="${tabId}"]`);
    if (formEl) setFormStatus(formEl, error.message, 'error');
  }
}

tabButtons.forEach((btn) => btn.addEventListener('click', () => activateTab(btn.dataset.tab)));

entryForms.forEach((formEl) => {
  const tabId = formEl.dataset.tabForm;
  const cancelButton = formEl.querySelector('.form-cancel');

  formEl.addEventListener('submit', async (event) => {
    event.preventDefault();
    await saveEntry(tabId, formEl);
  });

  formEl.elements.author.addEventListener('input', (event) => {
    const author = event.target.value;
    localStorage.setItem(STORAGE_KEYS.author, author);
    syncAuthorInputs(author);
  });

  cancelButton.addEventListener('click', () => resetForm(tabId));
});

entryLists.forEach((listEl, tabId) => {
  listEl.addEventListener('click', async (event) => {
    const button = event.target.closest('[data-entry-action]');
    if (!button) return;

    const { entryAction, entryId } = button.dataset;
    if (entryAction === 'edit') beginEdit(tabId, entryId);
    if (entryAction === 'delete') await deleteEntry(tabId, entryId);
  });
});

const savedTab = localStorage.getItem(STORAGE_KEYS.activeTab);
if (savedTab && BOARD_TABS.includes(savedTab)) activateTab(savedTab);

const savedAuthor = localStorage.getItem(STORAGE_KEYS.author) || '';
syncAuthorInputs(savedAuthor);
renderBoard();
loadBoard();
window.setInterval(() => loadBoard({ silent: true }), POLL_INTERVAL_MS);
