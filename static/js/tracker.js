// static/js/tracker.js
(function () {
  'use strict';

  // ---------- Tiny helpers ----------
  const $  = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  // ---------- Re-open a modal if we asked to keep it open ----------
  (function reopenModalIfRequested() {
    const id = sessionStorage.getItem('reopenModal');
    if (!id) return;
    sessionStorage.removeItem('reopenModal');
    const el = document.getElementById(id);
    if (el && window.bootstrap) bootstrap.Modal.getOrCreateInstance(el).show();
  })();

  // Persist the open modal across full page reload on comment submit/delete
  $$('.modal form[action*="/comment"]').forEach((form) => {
    const modal = form.closest('.modal');
    if (!modal) return;
    form.addEventListener('submit', () => {
      sessionStorage.setItem('reopenModal', modal.id);
    });
  });

  // ---------- Field visibility (no status/rating) ----------
  const FIELD_GROUPS = {
    chapters:       ['book','manga','manhwa'],
    seasons:        ['show','anime'],
    year:           ['movie','game'],
    runtime:        ['movie'],
    platforms:      ['game'],
    release_status: ['book','manga','manhwa','show','anime'],
  };

  function showFieldsForType(type, container){
    Object.entries(FIELD_GROUPS).forEach(([field, types])=>{
      container.querySelectorAll(`[data-field="${field}"]`).forEach(el=>{
        el.classList.toggle('d-none', !types.includes(type));
      });
    });
  }

  function initScoped(form){
    const typeSel = form.querySelector('select[name="media_type"]');
    if (!typeSel) return;
    const container = form;
    const apply = ()=> showFieldsForType((typeSel.value || '').toLowerCase(), container);
    typeSel.addEventListener('change', apply);
    apply(); // initial
  }

  // Initialize forms in both "New" and "Edit" modals
  document.addEventListener('shown.bs.modal', (e)=>{
    const form = e.target.querySelector('form');
    if (form) initScoped(form);
  });
  // In case "New Item" / Edit modals are already in DOM:
  $$('#newItemModal form, [id^="itemEdit"] form').forEach(initScoped);
})();

// ---- Load-more comments per modal ----
(function () {
  function initLoadMore(modal) {
    const list = modal.querySelector('.comments-scroll');
    if (!list) return;
    const cards = Array.from(list.querySelectorAll('.comment-card'));
    const btn   = list.querySelector('.btn-load-more');
    const initial = parseInt(list.dataset.initial || '2', 10);
    const step    = parseInt(btn?.dataset.step || '5', 10);

    if (!cards.length) { if (btn) btn.classList.add('d-none'); return; }

    let shown = Math.min(initial, cards.length);
    function render() {
      cards.forEach((el, i) => el.classList.toggle('d-none', i >= shown));
      if (btn) btn.classList.toggle('d-none', shown >= cards.length);
    }
    render();

    if (btn) {
      btn.addEventListener('click', () => {
        shown = Math.min(shown + step, cards.length);
        render();
      });
    }
  }

  // init whenever a tracker modal opens
  document.addEventListener('shown.bs.modal', (e) => {
    if (e.target.matches('.modal')) initLoadMore(e.target);
  });
})();

// --- Clickable rows (open modal) & keyboard support ---
document.addEventListener('click', (e) => {
  // If clicking something marked as row-ignore (e.g., Edit), don't bubble to the row
  if (e.target.closest('[data-row-ignore]')) {
    e.stopPropagation();
  }
});

document.addEventListener('keydown', (e) => {
  const row = e.target.closest('tr.media-row[role="button"]');
  if (!row) return;
  if (e.key === 'Enter' || e.key === ' ') {
    e.preventDefault();
    row.click(); // Bootstrap handles [data-bs-toggle="modal"]
  }
});
