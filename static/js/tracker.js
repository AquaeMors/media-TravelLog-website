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
  // If clicking something marked as row-ignore (e.g., Edit / tag pill / See all), don't bubble to the row
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

// --- Responsive tag-list collapsing (phones show first 3, then "See all") ---
(function () {
  const SM_MAX = 575; // <576px
  const debounce = (fn, t = 120) => {
    let id; return (...a) => { clearTimeout(id); id = setTimeout(() => fn.apply(null, a), t); };
  };

  function collapse(list, threshold) {
    const pills = list.querySelectorAll('.tag-pill');
    pills.forEach((el, i) => { el.hidden = i >= threshold; });

    const more = list.querySelector('.tag-more[data-role="more"]');
    if (more) {
      const hiddenCount = Math.max(0, pills.length - threshold);
      if (hiddenCount > 0) {
        more.classList.remove('d-none');
        more.textContent = `See all (${hiddenCount})`;
      } else {
        more.classList.add('d-none');
      }
    }
    list.dataset.state = 'collapsed';
  }

  function expand(list) {
    list.querySelectorAll('.tag-pill').forEach(el => (el.hidden = false));
    const more = list.querySelector('.tag-more[data-role="more"]');
    if (more) more.textContent = 'See less';
    list.dataset.state = 'expanded';
  }

  function reset(list) {
    list.querySelectorAll('.tag-pill').forEach(el => (el.hidden = false));
    const more = list.querySelector('.tag-more[data-role="more"]');
    if (more) more.classList.add('d-none');
    list.removeAttribute('data-state');
  }

  function updateAll() {
    const isSmall = window.innerWidth <= SM_MAX;
    document.querySelectorAll('.tag-list').forEach(list => {
      const pills = list.querySelectorAll('.tag-pill');
      if (!pills.length) { reset(list); return; }
      const threshold = parseInt(list.dataset.maxXs || '3', 10);

      if (isSmall && pills.length > threshold) {
        if (list.dataset.state === 'expanded') {
          expand(list);
        } else {
          collapse(list, threshold);
        }
      } else {
        reset(list);
      }
    });
  }

  // Toggle expand/collapse
  document.addEventListener('click', (e) => {
    const btn = e.target.closest('.tag-more[data-role="more"]');
    if (!btn) return;
    const list = btn.closest('.tag-list');
    if (list.dataset.state === 'collapsed') {
      expand(list);
    } else {
      const threshold = parseInt(list.dataset.maxXs || '3', 10);
      collapse(list, threshold);
    }
  });

  window.addEventListener('resize', debounce(updateAll, 120));
  document.addEventListener('DOMContentLoaded', updateAll);
  if (document.readyState !== 'loading') updateAll();
})();

// ---- Responsive tag chips: collapse on small viewports ----
(function () {
  // Breakpoint-based minimums; we'll also refine by container width
  const BREAKS = [
    { mq: "(max-width: 575.98px)", limit: 3 }, // xs
    { mq: "(max-width: 767.98px)", limit: 5 }, // sm
    { mq: "(max-width: 991.98px)", limit: 6 }, // md
  ];

  function limitFor(list) {
    // Start with breakpoint limit
    for (const b of BREAKS) if (window.matchMedia(b.mq).matches) return b.limit;

    // On larger screens, roughly size by available width (avg chip ≈ 120px)
    const w = list.clientWidth || 0;
    return Math.max(6, Math.floor(w / 120));
  }

  function collapseList(list) {
    const pills = Array.from(list.querySelectorAll(".tag-pill"));
    if (!pills.length) return;

    const moreBtn = list.querySelector(".tag-more");
    // If the author provided a strict cap for phones, use it on xs
    let limit = limitFor(list);
    const maxXs = parseInt(list.dataset.maxXs || "0", 10);
    if (maxXs && window.matchMedia("(max-width: 575.98px)").matches) {
      limit = maxXs;
    }

    // Hide beyond the limit
    let hiddenCount = 0;
    pills.forEach((p, i) => {
      const hide = i >= limit;
      p.classList.toggle("d-none", hide);
      if (hide) hiddenCount++;
    });

    if (!moreBtn) return;

    // Show/Hide the "See all" pill
    moreBtn.classList.toggle("d-none", hiddenCount === 0);

    // Bind once
    if (!moreBtn.dataset.bound) {
      moreBtn.dataset.bound = "1";
      moreBtn.addEventListener("click", (e) => {
        e.stopPropagation(); // never trigger the row click
        pills.forEach((p) => p.classList.remove("d-none"));
        moreBtn.classList.add("d-none");
      });
    }
  }

  function initAll() {
    document.querySelectorAll(".tag-list").forEach(collapseList);
  }

  // Recalculate on resize/rotation per-list (more accurate than window resize)
  const ro = new ResizeObserver((entries) => {
    for (const entry of entries) collapseList(entry.target);
  });

  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll(".tag-list").forEach((el) => ro.observe(el));
    initAll();
  });

  // If your theme toggle flips layout metrics, recalc as well
  window.addEventListener("themechange", initAll);
})();
