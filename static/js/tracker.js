// /static/js/tracker.js
document.addEventListener("DOMContentLoaded", () => {
  // Auto-submit on status change (filter bar)
  const filterForm = document.getElementById("filterForm");
  document.getElementById("filter-status")?.addEventListener("change", () => filterForm?.submit());

  // Status vocab
  const DEFAULT_STATUSES = ["current","waiting","finished"];
  const SERIAL_STATUSES  = ["ongoing","completed","hiatus","canceled"];
  const SERIAL_TYPES     = new Set(["manga","manhwa"]);
  const CHAPTER_TYPES    = new Set(["book","manga","manhwa"]);

  function fillOptions(selectEl, list, selected) {
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

  // ---- New item modal ----
  const addTypeSel   = document.getElementById("add-media-type");
  const addStatusSel = document.getElementById("add-status");
  const addChWrap    = document.getElementById("chapter-fields");

  function updateNewFields() {
    const t = (addTypeSel?.value || "").toLowerCase();
    const serial = SERIAL_TYPES.has(t);
    fillOptions(addStatusSel, serial ? SERIAL_STATUSES : DEFAULT_STATUSES, null);
    if (addChWrap) addChWrap.classList.toggle("d-none", !CHAPTER_TYPES.has(t));
  }

  if (addTypeSel && addStatusSel) {
    updateNewFields();
    addTypeSel.addEventListener("change", updateNewFields);
  }

  // ---- Edit modals ----
  document.querySelectorAll(".js-edit-type").forEach(selType => {
    const statusId  = selType.dataset.statusTarget;
    const chWrapId  = selType.dataset.chapterTarget;
    const selStatus = document.getElementById(statusId);
    const chWrap    = document.getElementById(chWrapId);
    const current   = (selType.dataset.currentStatus || "").toLowerCase();

    function updateEditFields(initial=false) {
      const t = (selType.value || "").toLowerCase();
      const serial = SERIAL_TYPES.has(t);
      fillOptions(selStatus, serial ? SERIAL_STATUSES : DEFAULT_STATUSES, initial ? current : null);
      if (chWrap) chWrap.classList.toggle("d-none", !CHAPTER_TYPES.has(t));
    }
    updateEditFields(true);
    selType.addEventListener("change", () => updateEditFields(false));
  });
});
