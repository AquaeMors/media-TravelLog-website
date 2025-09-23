(function () {
  // Section metadata (now includes a distinct accent color per kind)
  const map = {
    boards: { title: "Boards", icon: "bi-images", sub: "Rings • Cakes • Photo ideas", color: "#8EC5FF" },
    links: { title: "Links", icon: "bi-link-45deg", sub: "Video & article references", color: "#D0B3FF" },
    venues: { title: "Venues & Vendors", icon: "bi-geo-alt", sub: "Candidates & notes", color: "#FFC78E" },
    ideas: { title: "Quick Ideas", icon: "bi-lightbulb", sub: "Inbox for snippets", color: "#85E0C2" },
    ceremony: { title: "Ceremony", icon: "bi-journal", sub: "Order, readings, communion", color: "#b6e01bff" },
    reception: { title: "Reception", icon: "bi-card-checklist", sub: "Program, speeches, tables", color: "#d3770eff" },
    tasks: { title: "Tasks", icon: "bi-check2-square", sub: "Checklist & owners", color: "#2668d3ff" },
    seating: { title: "Seating", icon: "bi-people", sub: "Tables & guests", color: "#ff76ddff" }, 
    budget:  { title: "Budget",  icon: "bi-cash-coin", sub: "Estimate vs actual", color: "#ff8f5bff" } 
  };


  // Track which kind is in which side (for toggling)
  const assigned = { left: null, right: null };

  // Make panels sit exactly below the fixed menu
  function measureMenu() {
    const menu = document.getElementById('panel-menu');
    if (menu) {
      const h = menu.offsetHeight || 52;
      document.documentElement.style.setProperty('--panel-menu-height', h + 'px');
    }
  }
  window.addEventListener('resize', measureMenu);
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', measureMenu);
  } else { measureMenu(); }

  function els(side) {
    return {
      panel: document.getElementById(side === 'left' ? 'panel-left' : 'panel-right'),
      body: document.getElementById(side === 'left' ? 'pl-body' : 'pr-body'),
      title: document.getElementById(side === 'left' ? 'pl-title' : 'pr-title'),
      icon: document.getElementById(side === 'left' ? 'pl-icon' : 'pr-icon'),
      sub: document.getElementById(side === 'left' ? 'pl-sub' : 'pr-sub'),
    };
  }
  function isOpen(side) { const p = els(side).panel; return p && p.classList.contains('open'); }

  // Decide next side: first click -> left; if left open -> right; if both open -> left.
  function nextSide() {
    if (!isOpen('left')) return 'left';
    if (!isOpen('right')) return 'right';
    return 'left';
  }

  function closePanel(side) {
    const { panel } = els(side);
    if (!panel) return;
    panel.classList.remove('open');
    panel.setAttribute('aria-hidden', 'true');
    // unmark active button bound to this side
    const active = document.querySelector(`#panel-menu .pm-btn[data-side-assigned="${side}"]`);
    if (active) {
      active.classList.remove('active');
      active.removeAttribute('data-side-assigned');
      active.style.removeProperty('--pm-color');
    }
    assigned[side] = null;
  }

  async function loadPanel(side, kind) {
    const E = els(side);
    const meta = map[kind];
    if (!E.panel || !meta) return;

    // Accent color sync: panel header + button color
    E.panel.style.setProperty('--panel-accent', meta.color);

    // Header
    E.title.textContent = meta.title;
    E.icon.className = "bi " + meta.icon;
    E.sub.textContent = meta.sub;

    // Skeleton
    E.body.innerHTML = '<div class="text-center py-5"><div class="spinner-border" role="status"></div></div>';

    // Fetch partial
    const r = await fetch(`/wedding/panel?kind=${encodeURIComponent(kind)}`, { credentials: 'same-origin' });
    E.body.innerHTML = await r.text();

    // Open
    E.panel.classList.add('open');
    E.panel.setAttribute('aria-hidden', 'false');

    // Mark button as active & bound to this side; clear any prior button on that side
    const old = document.querySelector(`#panel-menu .pm-btn[data-side-assigned="${side}"]`);
    if (old) {
      old.classList.remove('active');
      old.removeAttribute('data-side-assigned');
      old.style.removeProperty('--pm-color');
    }
    const btn = document.querySelector(`#panel-menu .pm-btn[data-kind="${kind}"]`);
    if (btn) {
      btn.classList.add('active');
      btn.dataset.sideAssigned = side;
      btn.style.setProperty('--pm-color', meta.color);
    }
    assigned[side] = kind;

    // Intercept forms (AJAX, then refresh this panel)
    E.body.querySelectorAll('form[data-panel-refresh]').forEach(form => {
      form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const b = form.querySelector('button[type="submit"],button:not([type])');
        if (b) b.disabled = true;
        try {
          await fetch(form.action, { method: form.method || 'POST', body: new FormData(form), credentials: 'same-origin' });
          await loadPanel(side, kind);
        } finally {
          if (b) b.disabled = false;
        }
      }, { once: true });
    });
  }

  function wire() {
    // Menu buttons
    document.querySelectorAll('#panel-menu .pm-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const kind = btn.dataset.kind;
        const boundSide = btn.dataset.sideAssigned;

        // If this button's section is already open on a side, clicking it collapses that panel
        if (boundSide && isOpen(boundSide)) {
          closePanel(boundSide);
          return;
        }

        // Otherwise open on the next appropriate side
        const side = nextSide();
        loadPanel(side, kind);
      });
    });

    // Close buttons on the panels
    document.querySelectorAll('[data-close]').forEach(b => {
      b.addEventListener('click', () => closePanel(b.dataset.close));
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', wire);
  } else { wire(); }
})();

// Keep panels under menu; also compress menu on scroll
function measureMenu(){
  const menu = document.getElementById('panel-menu');
  if (menu){
    const h = menu.offsetHeight || 52;
    document.documentElement.style.setProperty('--panel-menu-height', h + 'px');
  }
}
function handleScroll(){
  const bar = document.getElementById('panel-menu');
  if (!bar) return;
  const root = bar; // bar is the element with class w-menu-bar
  if (window.scrollY > 12) root.classList.add('compact');
  else root.classList.remove('compact');
}
window.addEventListener('resize', measureMenu);
window.addEventListener('scroll', handleScroll);
if (document.readyState === 'loading'){
  document.addEventListener('DOMContentLoaded', ()=>{ measureMenu(); handleScroll(); });
} else { measureMenu(); handleScroll(); }
