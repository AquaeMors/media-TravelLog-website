(function () {
  // ---- Section metadata (colors power the active menu pill glow) ----
  const map = {
    boards: { title: "Boards", icon: "bi-images", sub: "Rings • Cakes • Photo ideas", color: "#8EC5FF" },
    links: { title: "Links", icon: "bi-link-45deg", sub: "Video & article references", color: "#D0B3FF" },
    venues: { title: "Venues & Vendors", icon: "bi-geo-alt", sub: "Candidates & notes", color: "#FFC78E" },
    ideas: { title: "Quick Ideas", icon: "bi-lightbulb", sub: "Inbox for snippets", color: "#85E0C2" },
    ceremony: { title: "Ceremony", icon: "bi-journal", sub: "Order, readings, communion", color: "#b6e01b" },
    reception: { title: "Reception", icon: "bi-card-checklist", sub: "Program, speeches, tables", color: "#d3770e" },
    tasks: { title: "Tasks", icon: "bi-check2-square", sub: "Checklist & owners", color: "#2668d3" },
    seating: { title: "Seating", icon: "bi-people", sub: "Tables & guests", color: "#ff76dd" },
    budget: { title: "Budget", icon: "bi-cash-coin", sub: "Estimate vs actual", color: "#ff8f5b" }
  };

  function els(side) {
    return {
      panel: document.getElementById(side === 'left' ? 'panel-left' : 'panel-right'),
      body: document.getElementById(side === 'left' ? 'pl-body' : 'pr-body'),
      title: document.getElementById(side === 'left' ? 'pl-title' : 'pr-title'),
      icon: document.getElementById(side === 'left' ? 'pl-icon' : 'pr-icon'),
      sub: document.getElementById(side === 'left' ? 'pl-sub' : 'pr-sub')
    };
  }
  function isOpen(side) { const p = els(side).panel; return p && p.classList.contains('open'); }
  function nextSide() { if (!isOpen('left')) return 'left'; if (!isOpen('right')) return 'right'; return 'left'; }

  function closePanel(side) {
    const { panel } = els(side); if (!panel) return;
    panel.classList.remove('open'); panel.setAttribute('aria-hidden', 'true');
    const active = document.querySelector(`#panel-menu .pm-btn[data-side-assigned="${side}"]`);
    if (active) { active.classList.remove('active'); active.removeAttribute('data-side-assigned'); active.style.removeProperty('--pm-color'); }
  }

  /* -------- One place to handle all in-panel form submissions -------- */
  document.addEventListener('submit', async (e) => {
    const form = e.target;
    if (!form.matches('form[data-panel-refresh]')) return;

    e.preventDefault(); e.stopPropagation(); if (e.stopImmediatePropagation) e.stopImmediatePropagation();

    const panel = form.closest('.w-panel');
    const side = panel && panel.classList.contains('right') ? 'right' : 'left';
    const kind = panel?.dataset.kind || 'boards';

    const btn = form.querySelector('button[type="submit"],button:not([type])');
    if (btn) btn.disabled = true;

    try {
      await fetch(form.action, { method: form.method || 'POST', body: new FormData(form), credentials: 'same-origin' });

      // preserve optional parameters (e.g., sub=rings)
      const keep = form.getAttribute('data-panel-refresh-params') || '';
      const params = Object.fromEntries(new URLSearchParams(keep));
      await loadPanel(side, kind, params);     // refresh just this panel
      flashPanelCheck(side);                   // ✅ center pulse
    } finally { if (btn) btn.disabled = false; }
  }, true); // capture phase


  // Graceful AJAX delete for forms marked with data-ajax-delete
  document.addEventListener('submit', async (e) => {
    const form = e.target;
    if (!form.matches('form[data-ajax-delete]')) return;

    e.preventDefault(); e.stopPropagation();
    if (e.stopImmediatePropagation) e.stopImmediatePropagation();

    const panel = form.closest('.w-panel');
    const side = panel && panel.classList.contains('right') ? 'right' : 'left';

    // Find the node to animate/remove
    const sel = form.getAttribute('data-vanish-target');
    const target = sel ? form.closest(sel) : form.closest('.m-item, .list-row, .card');
    if (!target) {
      // Fallback: just POST and then refresh this panel
      await fetch(form.action, { method: form.method || 'POST', body: new FormData(form), credentials: 'same-origin' });
      flashPanelCheck(side);
      // optional: reload panel or sub here if you want, but not required
      return;
    }

    // Run the micro-transition, then POST, then remove
    target.classList.add('vanish');

    const doPost = () => fetch(form.action, {
      method: form.method || 'POST',
      body: new FormData(form),
      credentials: 'same-origin'
    });

    // Wait for the CSS transition (or 200ms timeout), then send request
    const done = new Promise(res => {
      const to = setTimeout(res, 200);
      target.addEventListener('transitionend', () => { clearTimeout(to); res(); }, { once: true });
    });

    await done;
    const r = await doPost();

    if (r.ok) {
      target.remove();
      flashPanelCheck(side);
    } else {
      // On failure, roll back the visual change
      target.classList.remove('vanish');
      // (We’ll add proper toasts in Step 4)
      console.warn('Delete failed', r.status);
    }
  }, true); // capture so it wins over other handlers


  /* ------------------ Panel loading ------------------ */
  async function loadPanel(side, kind, params = {}) {
    const E = els(side);
    const meta = map[kind]; if (!E.panel || !meta) return;

    E.panel.dataset.kind = kind;
    E.title.textContent = meta.title;
    E.icon.className = "bi " + meta.icon;
    E.sub.textContent = meta.sub;

    // lightweight skeleton
    E.body.innerHTML = '<div class="text-center py-5"><div class="spinner-border" role="status"></div></div>';

    const qs = new URLSearchParams({ kind });
    Object.entries(params).forEach(([k, v]) => { if (v != null) qs.set(k, v); });

    const r = await fetch('/wedding/panel?' + qs.toString(), { credentials: 'same-origin' });
    E.body.innerHTML = await r.text();

    E.panel.classList.add('open');
    E.panel.setAttribute('aria-hidden', 'false');

    // wire features that live inside the injected fragment
    if (kind === 'boards') {
      wireBoardTabs(E.body);
      wireEditableTitles(E.body);
      enableRipples(E.body);
    }
    enableRipples(E.body);
    bindStarToggles(E.body);
  }

  /* ----------------- Menu buttons + close ----------------- */
  function wire() {
    document.querySelectorAll('#panel-menu .pm-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const kind = btn.dataset.kind;
        const bound = btn.dataset.sideAssigned;
        if (bound && isOpen(bound)) { closePanel(bound); return; }
        const side = nextSide();
        loadPanel(side, kind);
      });
    });
    document.querySelectorAll('[data-close]').forEach(b => {
      b.addEventListener('click', () => closePanel(b.dataset.close));
    });
  }

  // Menu height + compact shadow on scroll
  function measureMenu() {
    const m = document.getElementById('panel-menu'); if (!m) return;
    document.documentElement.style.setProperty('--panel-menu-height', (m.offsetHeight || 52) + 'px');
  }
  function handleScroll() {
    const bar = document.getElementById('panel-menu'); if (!bar) return;
    if (window.scrollY > 12) bar.classList.add('compact'); else bar.classList.remove('compact');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => { wire(); measureMenu(); handleScroll(); });
  } else { wire(); measureMenu(); handleScroll(); }
  window.addEventListener('resize', measureMenu);
  window.addEventListener('scroll', handleScroll);
})();

/* ---------------- Success pulse in panel center ---------------- */
function flashPanelCheck(side) {
  const panel = document.getElementById(side === 'left' ? 'panel-left' : 'panel-right'); if (!panel) return;
  const old = panel.querySelector('.panel-pulse'); if (old) old.remove();
  const pulse = document.createElement('div'); pulse.className = 'panel-pulse';
  pulse.innerHTML = `<svg viewBox="0 0 64 64" focusable="false" aria-hidden="true">
    <circle class="pp-circ" cx="32" cy="32" r="26" stroke-width="4"></circle>
    <path class="pp-path" d="M18 33.5l9 8 20-22" stroke-width="6"></path>
  </svg>`;
  panel.appendChild(pulse);
  requestAnimationFrame(() => { pulse.classList.add('show'); setTimeout(() => { pulse.classList.add('fade'); pulse.addEventListener('animationend', () => pulse.remove(), { once: true }); }, 900); });
}

/* ---------------- Boards: tabs slide + inline rename ---------------- */
function wireBoardTabs(scope) {
  const bar = scope.querySelector('.board-tabs'); if (!bar || bar.dataset.wired) return; bar.dataset.wired = '1';
  const content = scope.querySelector('.board-content'); if (!content) return;
  const tabs = bar.querySelectorAll('.tab');

  // initial index from CSS var
  const getActiveIndex = () => {
    const inline = bar.style.getPropertyValue('--active-index');
    if (inline) return parseInt(inline, 10) || 0;
    const cs = getComputedStyle(bar).getPropertyValue('--active-index');
    return parseInt(cs, 10) || 0;
  };
  let prevIndex = getActiveIndex();

  tabs.forEach((tab, i) => {
    tab.addEventListener('click', async (ev) => {
      ev.preventDefault(); ev.stopPropagation();
      if (tab.classList.contains('active')) return;

      bar.style.setProperty('--active-index', String(i));
      tabs.forEach(t => t.classList.toggle('active', t === tab));

      const sub = tab.dataset.boardSub;
      const dir = (i > prevIndex) ? 'right' : 'left';
      prevIndex = i;

      const res = await fetch(`/wedding/panel?kind=boards&sub=${encodeURIComponent(sub)}&starred=${bar.dataset.starred || '0'}`, { credentials: 'same-origin' });
      const html = await res.text();
      const tmp = document.createElement('div'); tmp.innerHTML = html;
      const fresh = tmp.querySelector('.board-content');
      const inner = fresh ? fresh.innerHTML : html;

      await slideSwap(content, inner, dir);

      // features inside swapped content:
      wireEditableTitles(content);
      bindStarFilter(content, bar);
      enableRipples(content);
    }, { passive: false });
  });
}

// Wire star toggles once per panel body; debounce clicks
function bindStarToggles(scope){
  // Attach the listener to the panel body (stable element)
  const host = scope.closest?.('.w-body') || scope;
  if (!host || host.dataset.starWired === '1') return;
  host.dataset.starWired = '1';

  host.addEventListener('click', async (e)=>{
    const btn = e.target.closest('.btn-star-toggle');
    if (!btn) return;

    e.preventDefault();
    e.stopPropagation();

    // debounce: ignore if a request is already in-flight for this button
    if (btn.dataset.busy === '1') return;
    btn.dataset.busy = '1';

    try {
      const id = btn.dataset.starId;
      const res = await fetch(`/wedding/item/${id}/star`, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'X-Requested-With': 'XMLHttpRequest' }
      });
      if (!res.ok) return;
      const data = await res.json();

      btn.classList.toggle('active', data.starred);
      btn.setAttribute('aria-pressed', data.starred ? 'true' : 'false');
      const icon = btn.querySelector('i');
      if (icon) icon.className = data.starred ? 'bi bi-star-fill' : 'bi bi-star';

      // If "Starred only" filter is ON and we just unstarred, remove the card
      const panel = btn.closest('.w-panel');
      const side  = panel && panel.classList.contains('right') ? 'right' : 'left';
      const bar   = panel?.querySelector('.board-tabs');
      const starredOnly = bar?.dataset?.starred === '1';
      if (starredOnly && !data.starred) {
        const item = btn.closest('.m-item');
        if (item) { item.classList.add('vanish'); setTimeout(()=> item.remove(), 200); }
      }

      flashPanelCheck(side);
    } finally {
      // small delay so double-clicks don’t spam
      setTimeout(()=> { btn.dataset.busy = '0'; }, 150);
    }
  }, true); // capture to win over other delegates
}


// Wire the "Starred only" filter; persists via dataset on the tab bar
function bindStarFilter(content, bar) {
  const ctl = content.querySelector('.star-filter');
  if (!ctl) return;

  // reflect current state from bar
  const on = (bar.dataset.starred === '1');
  ctl.setAttribute('aria-pressed', on ? 'true' : 'false');
  const ic = ctl.querySelector('i');
  if (ic) ic.className = on ? 'bi bi-star-fill' : 'bi bi-star';

  ctl.addEventListener('click', async () => {
    const nowOn = !(bar.dataset.starred === '1');
    bar.dataset.starred = nowOn ? '1' : '0';

    // fetch current sub with new filter
    const sub = bar.querySelector('.tab.active')?.dataset.boardSub || bar.dataset.currentSub || 'rings';
    const url = `/wedding/panel?kind=boards&sub=${encodeURIComponent(sub)}&starred=${nowOn ? '1' : '0'}`;
    const res = await fetch(url, { credentials: 'same-origin' });
    const html = await res.text();
    const tmp = document.createElement('div'); tmp.innerHTML = html;
    const fresh = tmp.querySelector('.board-content');
    const inner = fresh ? fresh.innerHTML : html;

    const region = content; // slide inside the content area only
    await slideSwap(region, inner, nowOn ? 'right' : 'left');

    // re-bind inside swapped content
    bindStarToggles(region);
    wireEditableTitles(region); // still need rename hooks
    bindStarFilter(region, bar);
    enableRipples(region);
  }, { passive: true });
}

function slideSwap(container, newInnerHTML, dir) {
  const h = container.clientHeight;
  const slider = document.createElement('div'); slider.style.position = 'relative'; slider.style.overflow = 'hidden'; slider.style.height = h + 'px';
  const oldSlide = document.createElement('div'); oldSlide.style.position = 'absolute'; oldSlide.style.inset = '0'; oldSlide.innerHTML = container.innerHTML;
  const newSlide = document.createElement('div'); newSlide.style.position = 'absolute'; newSlide.style.inset = '0'; newSlide.innerHTML = newInnerHTML;
  newSlide.style.transform = `translateX(${dir === 'right' ? '100%' : '-100%'})`;
  slider.append(oldSlide, newSlide); container.innerHTML = ''; container.appendChild(slider);
  newSlide.offsetHeight;
  const dur = 280; oldSlide.style.transition = `transform ${dur}ms ease`; newSlide.style.transition = `transform ${dur}ms ease`;
  oldSlide.style.transform = `translateX(${dir === 'right' ? '-100%' : '100%'})`; newSlide.style.transform = 'translateX(0)';
  return new Promise(resolve => { newSlide.addEventListener('transitionend', () => { container.innerHTML = newInnerHTML; resolve(); }, { once: true }); });
}

function wireEditableTitles(scope) {
  scope.querySelectorAll('[data-editable-title]').forEach(span => {
    span.addEventListener('dblclick', () => {
      const id = span.dataset.id; const old = span.textContent.trim();
      const input = document.createElement('input'); input.type = 'text'; input.className = 'form-control form-control-sm'; input.value = old; input.style.maxWidth = '70%';
      span.replaceWith(input); input.focus(); input.select();

      const swapBack = (text) => { const s = document.createElement('span'); s.className = 'img-label'; s.setAttribute('data-editable-title', ''); s.dataset.id = id; s.textContent = text; input.replaceWith(s); wireEditableTitles(scope); };

      const done = (save) => {
        const next = input.value.trim();
        if (save) {
          const fd = new FormData(); fd.append('title', next);
          fetch(`/wedding/item/${id}/title`, { method: 'POST', body: fd, credentials: 'same-origin' }).then(() => {
            const panel = scope.closest('.w-panel'); const side = panel && panel.classList.contains('right') ? 'right' : 'left';
            flashPanelCheck(side); swapBack(next || old);
          });
        } else { swapBack(old); }
      };
      input.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); done(true); } if (e.key === 'Escape') { e.preventDefault(); done(false); } });
      input.addEventListener('blur', () => done(true));
    });
  });
}

// Attach ripples to primary buttons inside a scope (panel body)
function enableRipples(scope) {
  if (!scope) return;
  scope.querySelectorAll('.btn-primary:not(.no-ripple)').forEach(btn => {
    // guard: wire once
    if (btn.dataset.rippleWired) return;
    btn.dataset.rippleWired = '1';
    btn.addEventListener('click', (e) => {
      if (btn.disabled) return;
      // Create ripple
      const rect = btn.getBoundingClientRect();
      const size = Math.max(rect.width, rect.height);
      const x = (e.clientX ?? (rect.left + rect.width / 2)) - rect.left - size / 2;
      const y = (e.clientY ?? (rect.top + rect.height / 2)) - rect.top - size / 2;

      const r = document.createElement('span');
      r.className = 'ripple';
      r.style.width = r.style.height = size + 'px';
      r.style.left = x + 'px';
      r.style.top = y + 'px';
      btn.appendChild(r);
      r.addEventListener('animationend', () => r.remove(), { once: true });
    }, { passive: true });
  });
}
