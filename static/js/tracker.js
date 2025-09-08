// /static/js/tracker.js
document.addEventListener("DOMContentLoaded", () => {
  // Auto-submit on status change (filter bar)
  const filterForm = document.getElementById("filterForm");
  const filterStatus = document.getElementById("filter-status");
  if (filterForm && filterStatus) {
    filterStatus.addEventListener("change", () => filterForm.submit());
  }

  // Per-type status options
  const STATUS_MAP = {
    book:   ["ongoing","completed","hiatus","canceled"],
    manga:  ["ongoing","completed","hiatus","canceled"],
    manhwa: ["ongoing","completed","hiatus","canceled"],
    movie:  ["released","upcoming","canceled"],
    show:   ["ongoing","completed","hiatus","canceled"],
    anime:  ["ongoing","completed","hiatus","canceled"],
    game:   ["released","in development","canceled"],
    other:  ["ongoing","completed","hiatus","canceled"],
  };

  function fillStatusOptions(selectEl, list, selected) {
    if (!selectEl) return;
    selectEl.innerHTML = "";
    list.forEach(v => {
      const opt = document.createElement("option");
      opt.value = v;
      opt.textContent = v.charAt(0).toUpperCase() + v.slice(1);
      if (selected && selected.toLowerCase() === v) opt.selected = true;
      selectEl.appendChild(opt);
    });
  }

  // “New Item” modal
  const addTypeSel = document.getElementById("add-media-type");
  const addStatusSel = document.getElementById("add-status");
  function updateAddStatus() {
    if (!addTypeSel || !addStatusSel) return;
    const v = (addTypeSel.value || "").toLowerCase();
    const list = STATUS_MAP[v] || STATUS_MAP.other;
    fillStatusOptions(addStatusSel, list, null);
  }
  if (addTypeSel && addStatusSel) {
    updateAddStatus();
    addTypeSel.addEventListener("change", updateAddStatus);
  }

  // Edit modals (use data-* to pass current status/target select id)
  document.querySelectorAll(".js-edit-type").forEach(selType => {
    const targetId = selType.dataset.statusTarget;
    const selStatus = document.getElementById(targetId);
    const currentStatus = (selType.dataset.currentStatus || "").toLowerCase();

    function updateEditStatus(initial = false) {
      const v = (selType.value || "").toLowerCase();
      const list = STATUS_MAP[v] || STATUS_MAP.other;
      fillStatusOptions(selStatus, list, initial ? currentStatus : null);
    }

    updateEditStatus(true);
    selType.addEventListener("change", () => updateEditStatus(false));
  });

  // STAR PICKER (1–5)
  function renderStars(container, value) {
    container.querySelectorAll(".star-btn").forEach(btn => {
      const n = parseInt(btn.dataset.star, 10);
      const icon = btn.querySelector("i");
      if (value >= n) {
        icon.classList.remove("bi-star","text-muted");
        icon.classList.add("bi-star-fill","text-warning");
      } else {
        icon.classList.remove("bi-star-fill","text-warning");
        icon.classList.add("bi-star","text-warning"); // keep yellow outline look
      }
    });
  }

  document.querySelectorAll(".star-picker").forEach(picker => {
    const targetId = picker.dataset.target;
    const input = document.getElementById(targetId);
    let current = parseInt(picker.dataset.current || "0", 10) || 0;

    // initial render
    renderStars(picker, current);

    picker.querySelectorAll(".star-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        const n = parseInt(btn.dataset.star, 10);
        current = n;
        if (input) input.value = String(current);
        renderStars(picker, current);
      });
    });
  });
});

