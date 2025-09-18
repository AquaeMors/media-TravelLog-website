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

/* ------------------------------------------------------------------
   Option B: Programmatic row modal control (no data-bs-toggle on <tr>)
   - Clicks on interactive elements (links, buttons, inputs, .js-add-tag,
     [data-row-ignore], .tag-more) DO NOT open the row modal.
   - Clicks on the rest of the row DO open the modal via JS.
   - Works with either:
       data-row-modal="#item123"  ← preferred
     or data-bs-target="#item123" ← fallback until you update markup
------------------------------------------------------------------ */
(function () {
  const INTERACTIVE_SEL = 'a,button,[role="button"],input,select,textarea,label,[data-row-ignore],.js-add-tag,.tag-more';

  function isInteractiveClick(target) {
    return !!target.closest(INTERACTIVE_SEL);
  }

  // Handle mouse/tap in CAPTURE to beat Bootstrap's own delegation (if present)
  document.addEventListener('click', (e) => {
    const row = e.target.closest('tr.media-row[role="button"]');
    if (!row) return;

    // Ignore clicks on pills/controls/etc.
    if (isInteractiveClick(e.target)) return;

    const sel = row.getAttribute('data-row-modal') || row.getAttribute('data-bs-target');
    if (!sel) return;

    e.preventDefault();
    e.stopImmediatePropagation();
    e.stopPropagation();

    const modalEl = document.querySelector(sel);
    if (modalEl && window.bootstrap) {
      bootstrap.Modal.getOrCreateInstance(modalEl).show();
    }
  }, true); // capture

  // Keyboard: Enter/Space on focused row opens modal
  document.addEventListener('keydown', (e) => {
    const row = e.target.closest('tr.media-row[role="button"]');
    if (!row) return;
    if (e.key !== 'Enter' && e.key !== ' ') return;

    // Don't hijack if the focused element is an input/button inside the row
    if (isInteractiveClick(e.target)) return;

    e.preventDefault();

    const sel = row.getAttribute('data-row-modal') || row.getAttribute('data-bs-target');
    if (!sel) return;

    const modalEl = document.querySelector(sel);
    if (modalEl && window.bootstrap) {
      bootstrap.Modal.getOrCreateInstance(modalEl).show();
    }
  });
})();

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

// ===== Dynamic tag filtering (no full page reload) =====
(function () {
  const form = document.getElementById('filterForm');
  if (!form) return;

  const type = () => form.querySelector('input[name="type"]')?.value || 'book';
  const qInp = form.querySelector('input[name="q"]');
  const activeTagsWrap = document.getElementById('activeTags');

  // read existing tags from the URL (supports repeated ?tag=)
  const url = new URL(location.href);
  const tagSet = new Set(url.searchParams.getAll('tag').map(t => (t || '').toLowerCase()));

  function buildQuery() {
    const params = new URLSearchParams();
    params.set('type', type());
    const qVal = (qInp?.value || '').trim();
    if (qVal) params.set('q', qVal);
    for (const t of tagSet) params.append('tag', t);
    return params;
  }

  async function refreshRows() {
    const params = buildQuery();
    // Update URL bar without reload
    history.replaceState(null, '', `${location.pathname}?${params.toString()}`);

    // Fetch fresh tbody HTML
    const res = await fetch(`/tracker/rows?${params.toString()}`, { headers: { 'X-Requested-With': 'fetch' } });
    const html = await res.text();
    const tbody = document.getElementById('rows-tbody');
    if (tbody) {
      // replace the whole <tbody id="rows-tbody"> with the new one
      tbody.outerHTML = html;
    }
    renderActiveTags();
  }

  function renderActiveTags() {
    if (!activeTagsWrap) return;
    if (!tagSet.size) {
      activeTagsWrap.innerHTML = '';
      return;
    }

    activeTagsWrap.innerHTML = `
      <div class="d-flex flex-wrap gap-1 mt-1">
        ${[...tagSet].map(t => `
          <span class="pill tag-pill">
            ${t}
            <button type="button" class="btn-close ms-1" aria-label="Remove ${t}" data-remove-tag="${t}"></button>
          </span>`).join('')}
        <a href="#" class="pill" id="clearAllTags" title="Clear all tags">Clear all</a>
      </div>
    `;
  }

  function addTag(t) {
    const tag = (t || '').trim().toLowerCase();
    if (!tag || tagSet.has(tag)) return;
    tagSet.add(tag);
    refreshRows();
  }

  function removeTag(t) {
    tagSet.delete(t);
    refreshRows();
  }

  // Intercept clicks on tag pills (table + modals)
  document.addEventListener('click', (e) => {
    const a = e.target.closest('.js-add-tag');
    if (a) {
      e.preventDefault();
      e.stopImmediatePropagation();
      e.stopPropagation(); // never reach row/modal handlers
      const tag = a.getAttribute('data-tag');
      addTag(tag);
      return;
    }
    const rm = e.target.closest('[data-remove-tag]');
    if (rm) {
      e.preventDefault();
      e.stopPropagation();
      removeTag(rm.getAttribute('data-remove-tag'));
      return;
    }
    if (e.target.id === 'clearAllTags') {
      e.preventDefault();
      e.stopPropagation();
      tagSet.clear();
      refreshRows();
    }
  });

  // If you submit the Filter form, keep it ajaxy too
  form.addEventListener('submit', (e) => {
    e.preventDefault();
    refreshRows();
  });

  // initial paint of active tag chips
  renderActiveTags();
})();
