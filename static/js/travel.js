// static/js/travel.js
(function () {
  'use strict';

  // ---------- Tiny helpers ----------
  const $  = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const escapeHtml = (s) =>
    s ? s.replace(/[&<>"']/g, (m) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m])) : '';

  // ---------- Main Leaflet map ----------
  const mapEl = document.getElementById('map');
  if (!mapEl || typeof L === 'undefined') return;

  const map = L.map('map', { scrollWheelZoom: true, worldCopyJump: true }).setView([20, 0], 2);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; OpenStreetMap contributors'
  }).addTo(map);

  const markers = [];

  function addMarkerFromTrip(t) {
    // Use a standard marker like your original inline script
    const m = L.marker([t.lat, t.lon]).addTo(map);

    // Popup HTML matches your inline version so existing CSS/behavior keeps working
    const popupHtml = `<strong>${escapeHtml(t.title)}</strong><br>
      <a href="#" data-open="#trip${t.id}">Open trip</a>`;
    m.bindPopup(popupHtml);

    // When popup opens, wire the "Open trip" link to Bootstrap modal
    m.on('popupopen', (e) => {
      // Leaflet 1.9: get the DOM node of this popup
      const node = e.popup && e.popup.getElement ? e.popup.getElement() : null;
      if (!node) return;
      const link = node.querySelector('[data-open]');
      if (!link) return;

      const sel = link.getAttribute('data-open');
      link.addEventListener('click', (ev) => {
        ev.preventDefault();
        const modalEl = document.querySelector(sel);
        if (modalEl && window.bootstrap) {
          bootstrap.Modal.getOrCreateInstance(modalEl).show();
        }
      }, { once: true });
    });

    markers.push(m);
  }

  // Load pins from API
  fetch('/api/trips', { headers: { 'Accept': 'application/json' } })
    .then((r) => r.json())
    .then((list) => {
      if (!Array.isArray(list)) return;
      list.forEach(addMarkerFromTrip);
    })
    .catch(() => { /* ignore network errors for now */ });

  // Zoom-to-pins button (support BOTH old id="zoomPins" and new id="fitPinsBtn")
  const zoomBtn = document.getElementById('fitPinsBtn') || document.getElementById('zoomPins');
  zoomBtn?.addEventListener('click', () => {
    if (!markers.length) return;
    const group = L.featureGroup(markers);
    map.fitBounds(group.getBounds().pad(0.2));
  });

  // ---------- "Show all photos" (legacy lazy-load behavior) ----------
  // Matches your old HTML: button[data-show-all][data-trip-id] + .lazy-wrap blocks in the modal
  $$('[data-show-all]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const id = btn.dataset.tripId;
      const modal = document.getElementById(`trip${id}`);
      if (!modal) return;

      modal.querySelectorAll('.lazy-wrap').forEach((wrap) => {
        const img = wrap.querySelector('img');
        const a   = wrap.querySelector('a');
        if (img && wrap.dataset.src)  img.src  = wrap.dataset.src;
        if (a && wrap.dataset.href)   a.href   = wrap.dataset.href;
        wrap.classList.remove('d-none');
      });

      btn.classList.add('d-none');
    });
  });

  // ---------- Address autocomplete (safe no-op if elements absent) ----------
  function attachAutocomplete(inputEl, boxEl) {
    let debounceTimer = null, aborter = null;

    inputEl.addEventListener('input', () => {
      const q = inputEl.value.trim();

      if (debounceTimer) clearTimeout(debounceTimer);
      if (q.length < 3) { boxEl.classList.add('d-none'); boxEl.innerHTML = ''; return; }

      debounceTimer = setTimeout(async () => {
        try {
          if (aborter) aborter.abort();
          aborter = new AbortController();
          const url = `https://nominatim.openstreetmap.org/search?format=json&addressdetails=1&limit=5&q=${encodeURIComponent(q)}`;
          const res = await fetch(url, { signal: aborter.signal, headers: { 'Accept': 'application/json' } });
          const data = await res.json();
          if (!Array.isArray(data) || !data.length) { boxEl.classList.add('d-none'); boxEl.innerHTML = ''; return; }

          boxEl.innerHTML = data.map((item) => {
            const disp = escapeHtml(item.display_name);
            return `<button type="button" class="list-group-item list-group-item-action" data-display="${disp}">${disp}</button>`;
          }).join('');
          boxEl.classList.remove('d-none');
        } catch(_) { /* ignore */ }
      }, 250);
    });

    boxEl.addEventListener('click', (e) => {
      const btn = e.target.closest('button[data-display]');
      if (!btn) return;
      inputEl.value = btn.getAttribute('data-display');
      boxEl.classList.add('d-none');
    });

    document.addEventListener('click', (e) => {
      if (!inputEl.closest('.addr-container')) boxEl.classList.add('d-none');
    });
  }

  const newAddr = document.getElementById('addr-input');
  const newBox  = document.getElementById('addr-suggestions');
  if (newAddr && newBox) attachAutocomplete(newAddr, newBox);

  // For any edit modals you may add later
  $$('[id^="addr-input-edit-"]').forEach((inp) => {
    const id  = inp.id.replace('addr-input-edit-', '');
    const box = document.getElementById('addr-suggestions-edit-' + id);
    if (box) attachAutocomplete(inp, box);
  });

  // ---------- Mini map pickers (safe no-op if elements absent) ----------
  function initPicker(mapDivId, latInput, lonInput, startLat = null, startLon = null) {
    const m = L.map(mapDivId, {
      center: [startLat ?? 20, startLon ?? 0],
      zoom: startLat != null ? 10 : 2,
      scrollWheelZoom: true
    });
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19 }).addTo(m);

    let marker = null;
    function setMarker(lat, lon) {
      if (marker) marker.setLatLng([lat, lon]);
      else marker = L.marker([lat, lon]).addTo(m);
      if (latInput) latInput.value = Number(lat).toFixed(6);
      if (lonInput) lonInput.value = Number(lon).toFixed(6);
    }

    if (startLat != null && startLon != null) setMarker(startLat, startLon);
    m.on('click', (e) => setMarker(e.latlng.lat, e.latlng.lng));
    return { map: m, setMarker };
  }

  async function geocodeInto(addrStr, latEl, lonEl, pickerObj = null) {
    try {
      const url = `https://nominatim.openstreetmap.org/search?format=json&limit=1&q=${encodeURIComponent(addrStr)}`;
      const res = await fetch(url);
      const data = await res.json();
      if (Array.isArray(data) && data.length) {
        const lat = parseFloat(data[0].lat);
        const lon = parseFloat(data[0].lon);
        if (latEl) latEl.value = lat.toFixed(6);
        if (lonEl) lonEl.value = lon.toFixed(6);
        if (pickerObj) {
          pickerObj.setMarker(lat, lon);
          pickerObj.map.setView([lat, lon], 12);
        }
      } else {
        alert('Could not geocode that address. Try adjusting it or set the pin manually.');
      }
    } catch(_) {
      alert('Geocoding error. Try again.');
    }
  }

  // New Location modal picker (if present)
  const newModal = document.getElementById('newLocationModal');
  let newPicker = null;
  if (newModal) {
    newModal.addEventListener('shown.bs.modal', () => {
      if (!newPicker) {
        newPicker = initPicker(
          'newloc-map',
          document.getElementById('new-lat'),
          document.getElementById('new-lon')
        );
      } else {
        newPicker.map.invalidateSize();
      }
    });

    const geoNewBtn = document.getElementById('geocode-new');
    if (geoNewBtn) {
      geoNewBtn.addEventListener('click', () =>
        geocodeInto(
          document.getElementById('addr-input').value,
          document.getElementById('new-lat'),
          document.getElementById('new-lon'),
          newPicker
        )
      );
    }
  }

  // Edit Trip modal pickers (if present)
  $$('[id^="editTrip"]').forEach((modal) => {
    let picker = null;
    modal.addEventListener('shown.bs.modal', () => {
      const id   = modal.id.replace('editTrip', '');
      const latEl = document.getElementById('lat-edit-' + id);
      const lonEl = document.getElementById('lon-edit-' + id);
      const lat = parseFloat(latEl && latEl.value);
      const lon = parseFloat(lonEl && lonEl.value);

      if (!picker) {
        picker = initPicker(
          'picker-' + id,
          latEl,
          lonEl,
          isFinite(lat) ? lat : null,
          isFinite(lon) ? lon : null
        );
      } else {
        picker.map.invalidateSize();
      }

      // Optional per-modal geocode button (data-geocode=".selectorToAddressInput")
      const btn = modal.querySelector('button[data-geocode]');
      if (btn && !btn._wired) {
        btn.addEventListener('click', () => {
          const addrSel = btn.getAttribute('data-geocode');
          const addrEl = addrSel ? modal.querySelector(addrSel) : null;
          if (addrEl) geocodeInto(addrEl.value, latEl, lonEl, picker);
        });
        btn._wired = true;
      }
    });
  });

  // ---------- (Optional) New gallery toggle variant ----------
  // If you later switch to the "gallery-toggle" pattern, this supports it too.
  document.addEventListener('click', (e) => {
    const btn = e.target.closest('.gallery-toggle');
    if (!btn) return;
    const target = btn.getAttribute('data-target');
    const wrap = document.querySelector(target);
    if (!wrap) return;

    const isCollapsed = wrap.classList.toggle('collapsed'); // toggled; true if now collapsed
    const expanded = !isCollapsed;

    btn.setAttribute('aria-expanded', String(expanded));
    const collapsedText = btn.getAttribute('data-collapsed-text') || 'Show all photos';
    const expandedText  = btn.getAttribute('data-expanded-text')  || 'Show less';
    btn.textContent = expanded ? expandedText : collapsedText;

    if (!expanded) btn.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  });
})();
