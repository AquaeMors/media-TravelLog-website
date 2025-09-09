// static/js/app.js
(function () {
  'use strict';

  /* =========================================================
     Theme toggle (light/dark) with system preference fallback
     - Works with a #themeToggle button if present
     - If not present in the navbar, we show a floating FAB (in base.html)
     ========================================================= */
  (function themeToggle() {
    const key = 'pref-theme';
    const root = document.documentElement;
    const btn = document.getElementById('themeToggle');

    function setIcon(theme) {
      if (!btn) return;
      const i = btn.querySelector('i');
      if (!i) return;
      i.className = 'bi ' + (theme === 'dark' ? 'bi-sun' : 'bi-moon-stars');
    }

    function apply(theme) {
      root.setAttribute('data-theme', theme);
      setIcon(theme);
    }

    let saved = localStorage.getItem(key);
    if (!saved) {
      saved = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }
    apply(saved);

    if (btn) {
      btn.addEventListener('click', () => {
        const next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
        localStorage.setItem(key, next);
        apply(next);
      });
    }
  })();

  // === Theme bridge: keep Bootstrap + native controls in sync with YOUR toggle ===
(function themeBridge() {
  const root = document.documentElement;
  const body = document.body;

  // Works with either: <html data-theme="dark"> OR <body data-theme="dark"> OR .theme-dark class
  const getTheme = () =>
    (root.getAttribute('data-theme') ||
     body.getAttribute('data-theme')  ||
     (root.classList.contains('theme-dark') || body.classList.contains('theme-dark') ? 'dark' : 'light'));

  const apply = () => {
    const t = getTheme();
    // Bootstrap 5.3 theme token
    body.setAttribute('data-bs-theme', t === 'dark' ? 'dark' : 'light');
    // Make native controls (open <select> panel) adopt the right palette immediately
    document.documentElement.style.colorScheme = (t === 'dark' ? 'dark' : 'light');
  };

  // React to your toggle changing classes/attributes
  new MutationObserver(apply).observe(root, { attributes: true, attributeFilter: ['data-theme', 'class'] });
  new MutationObserver(apply).observe(body, { attributes: true, attributeFilter: ['data-theme', 'class'] });
  window.addEventListener('DOMContentLoaded', apply);
  apply();
})();

  /* =========================================================
     Re-open modal after POST/redirect if form had data-keep-modal
     ========================================================= */
  function reopenModalIfRequested() {
    const id = sessionStorage.getItem('reopenModal');
    if (!id) return;
    sessionStorage.removeItem('reopenModal');
    const el = document.getElementById(id);
    if (el && window.bootstrap) {
      bootstrap.Modal.getOrCreateInstance(el).show();
    }
  }

  function wireKeepModalOnSubmit() {
    document.addEventListener('submit', (e) => {
      const form = e.target;
      if (!(form instanceof HTMLFormElement)) return;
      if (!form.hasAttribute('data-keep-modal')) return;
      const modal = form.closest('.modal');
      if (modal?.id) sessionStorage.setItem('reopenModal', modal.id);
    }, true);
  }

  /* =========================================================
     Optional confirm handler (opt-in via data-confirm)
     ========================================================= */
  function wireConfirm() {
    document.addEventListener('submit', (e) => {
      const form = e.target;
      if (!(form instanceof HTMLFormElement)) return;
      const msg = form.getAttribute('data-confirm');
      if (msg && !confirm(msg)) e.preventDefault();
    }, true);
  }

  /* =========================================================
     Time-ago formatter for [data-timeago]
     - < 60s: "just now"
     - 2+ mins (we start at 2 to avoid flicker)
     - hours
     - days
     ========================================================= */
  function fmtAgo(date) {
    const now = new Date();
    const diffSec = Math.max(0, (now - date) / 1000);

    if (diffSec < 60) return 'just now';

    if (diffSec < 3600) {
      const mins = Math.max(2, Math.floor(diffSec / 60));
      return `${mins} min${mins === 1 ? '' : 's'} ago`;
    }
    if (diffSec < 86400) {
      const hrs = Math.floor(diffSec / 3600);
      return `${hrs} hour${hrs === 1 ? '' : 's'} ago`;
    }
    const days = Math.floor(diffSec / 86400);
    return `${days} day${days === 1 ? '' : 's'} ago`;
  }
  function updateTimeagos() {
    document.querySelectorAll('[data-timeago]').forEach((el) => {
      const raw = el.getAttribute('data-timeago');
      const d = raw ? new Date(raw) : null;
      if (!d || isNaN(d.getTime())) return;
      el.textContent = fmtAgo(d);
      el.title = d.toLocaleString();
    });
  }

  /* =========================================================
     Reactions (like/dislike) — shared by tracker/travel
     ========================================================= */
  function setReactButton(btn, count, active){
    if(!btn) return;
    btn.setAttribute('aria-pressed', active ? 'true' : 'false');
    const span = btn.querySelector('.count');
    if(span) span.textContent = count;
    btn.classList.toggle('has-count', Number(count) > 0);
  }

  document.addEventListener('click', async (e) => {
    const btn = e.target.closest('.btn-react');
    if(!btn) return;

    const commentId = btn.getAttribute('data-comment-id');
    const action = btn.getAttribute('data-react'); // "like" | "dislike"
    const kind = btn.getAttribute('data-kind');     // "trip" | "item"

    try {
      const res = await fetch(`/api/comments/${encodeURIComponent(kind)}/${encodeURIComponent(commentId)}/react`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
        body: JSON.stringify({ action })
      });

      if (res.status === 401) { alert('Please sign in to react.'); return; }

      const data = await res.json();
      if (!data.ok) return;

      // update the two buttons for this comment
      const card = btn.closest('.comment-card') || document;
      const likeBtn = card.querySelector(`.btn-react[data-react="like"][data-comment-id="${commentId}"]`);
      const dislikeBtn = card.querySelector(`.btn-react[data-react="dislike"][data-comment-id="${commentId}"]`);
      setReactButton(likeBtn, data.likes, data.user_reaction === 'like');
      setReactButton(dislikeBtn, data.dislikes, data.user_reaction === 'dislike');
    } catch (err) {
      console.error(err);
    }
  });

  /* =========================================================
     Boot
     ========================================================= */
  document.addEventListener('DOMContentLoaded', () => {
    reopenModalIfRequested();
    wireKeepModalOnSubmit();
    wireConfirm();
    updateTimeagos();
    setInterval(updateTimeagos, 60_000);
  });
})();

// Faux-select shim: themed dropdown that mirrors a native <select>
// (Keeps form submission working; original <select> remains in the DOM.)
(function () {
  function enhanceSelect(select) {
    if (select._enhanced) return;
    select._enhanced = true;

    // container
    const wrap = document.createElement('div');
    wrap.className = 'dropdown faux-select w-100';

    // button that shows the current value
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'btn form-select d-flex justify-content-between align-items-center';
    btn.setAttribute('data-bs-toggle', 'dropdown');
    btn.setAttribute('aria-expanded', 'false');

    const label = document.createElement('span');
    label.className = 'faux-label flex-grow-1 text-truncate';
    label.textContent = select.options[select.selectedIndex]?.text || '—';

    const caret = document.createElement('i');
    caret.className = 'bi bi-caret-down-fill ms-2 opacity-50';

    btn.appendChild(label);
    btn.appendChild(caret);

    // menu
    const menu = document.createElement('ul');
    menu.className = 'dropdown-menu w-100';

    Array.from(select.options).forEach((opt) => {
      const li = document.createElement('li');
      const item = document.createElement('button');
      item.type = 'button';
      item.className = 'dropdown-item' + (opt.disabled ? ' disabled' : '');
      item.textContent = opt.text;
      item.dataset.value = opt.value;
      if (opt.selected) item.classList.add('active');

      item.addEventListener('click', () => {
        if (opt.disabled) return;
        select.value = opt.value;
        label.textContent = opt.text;
        // update active UI
        menu.querySelectorAll('.dropdown-item.active').forEach((a) => a.classList.remove('active'));
        item.classList.add('active');
        // bubble change for any listeners
        select.dispatchEvent(new Event('change', { bubbles: true }));
      });

      li.appendChild(item);
      menu.appendChild(li);
    });

    // insert before the select; keep select for submission
    select.insertAdjacentElement('beforebegin', wrap);
    wrap.appendChild(btn);
    wrap.appendChild(menu);

    // visually hide the select but leave it focusable via form APIs if needed
    select.classList.add('visually-hidden');
    select.tabIndex = -1;
  }

  function enhanceWithin(root) {
    root.querySelectorAll('select.form-select[data-faux-select]').forEach(enhanceSelect);
  }

  // enhance on page load for any already-present selects
  window.addEventListener('DOMContentLoaded', () => enhanceWithin(document));
  // enhance each modal the moment it opens
  document.addEventListener('shown.bs.modal', (e) => enhanceWithin(e.target));
})();
