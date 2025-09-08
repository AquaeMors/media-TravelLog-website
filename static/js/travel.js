(function () {
  // ---------- Utilities ----------
  const $ = (sel, root=document) => root.querySelector(sel);
  const $$ = (sel, root=document) => Array.from(root.querySelectorAll(sel));
  const escapeHtml = s => s ? s.replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m])) : '';

  // ---------- Leaflet: main map ----------
  const map = L.map('map', { scrollWheelZoom: true });
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '&copy; OpenStreetMap contributors' }).addTo(map);
  map.setView([20, 0], 2); // start zoomed out

  const markers = [];
  function addDot(id, lat, lon, title) {
    const m = L.circleMarker([lat, lon], { radius: 5 }).addTo(map);
    m.bindPopup(`<div class="small fw-semibold"><a href="#" class="open-trip" data-trip-id="${id}">${escapeHtml(title)}</a></div>`);
    m.on('popupopen', (e) => {
      const el = e.popup.getElement();
      const link = el ? el.querySelector('.open-trip') : null;
      if (link) {
        link.addEventListener('click', (ev) => {
          ev.preventDefault();
          const modalEl = document.getElementById('trip' + id);
          if (modalEl) bootstrap.Modal.getOrCreateInstance(modalEl).show();
        }, { once: true });
      }
    });
    markers.push(m);
  }

  fetch('/api/trips', { headers: { 'Accept': 'application/json' } })
    .then(r => r.json())
    .then(data => { if (Array.isArray(data)) data.forEach(t => addDot(t.id, t.lat, t.lon, t.title)); })
    .catch(() => {});

  $('#fitPinsBtn')?.addEventListener('click', () => {
    if (!markers.length) return;
    const group = L.featureGroup(markers);
    map.fitBounds(group.getBounds().pad(0.2));
  });

  // ---------- Address autocomplete (unchanged) ----------
  function attachAutocomplete(inputEl, boxEl) {
    let debounceTimer=null, aborter=null;
    inputEl.addEventListener('input', () => {
      const q = inputEl.value.trim();
      if (debounceTimer) clearTimeout(debounceTimer);
      if (q.length < 3) { boxEl.classList.add('d-none'); boxEl.innerHTML = ''; return; }
      debounceTimer = setTimeout(async () => {
        try {
          if (aborter) aborter.abort(); aborter = new AbortController();
          const url = `https://nominatim.openstreetmap.org/search?format=json&addressdetails=1&limit=5&q=${encodeURIComponent(q)}`;
          const res = await fetch(url, { signal: aborter.signal, headers: { 'Accept':'application/json' } });
          const data = await res.json();
          if (!Array.isArray(data) || data.length === 0) { boxEl.classList.add('d-none'); boxEl.innerHTML = ''; return; }
          boxEl.innerHTML = data.map(item => {
            const disp = escapeHtml(item.display_name);
            return `<button type="button" class="list-group-item list-group-item-action" data-display="${disp}">${disp}</button>`;
          }).join('');
          boxEl.classList.remove('d-none');
        } catch(e) {}
      }, 250);
    });
    boxEl.addEventListener('click', e => {
      const btn = e.target.closest('button[data-display]'); if (!btn) return;
      inputEl.value = btn.getAttribute('data-display'); boxEl.classList.add('d-none');
    });
    document.addEventListener('click', e => { if (!inputEl.closest('.addr-container')) boxEl.classList.add('d-none'); });
  }

  const newAddr = document.getElementById('addr-input');
  const newBox  = document.getElementById('addr-suggestions');
  if (newAddr && newBox) attachAutocomplete(newAddr, newBox);

  $$('[id^="addr-input-edit-"]').forEach(inp => {
    const id = inp.id.replace('addr-input-edit-', '');
    const box = document.getElementById('addr-suggestions-edit-' + id);
    if (box) attachAutocomplete(inp, box);
  });

  // ---------- Mini map pickers (unchanged) ----------
  function initPicker(mapDivId, latInput, lonInput, startLat=null, startLon=null) {
    const m = L.map(mapDivId, { center: [startLat ?? 20, startLon ?? 0], zoom: startLat ? 10 : 2, scrollWheelZoom: true });
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19 }).addTo(m);
    let marker = null;
    function setMarker(lat, lon) {
      if (marker) { marker.setLatLng([lat, lon]); }
      else { marker = L.marker([lat, lon]).addTo(m); }
      latInput.value = lat.toFixed(6);
      lonInput.value = lon.toFixed(6);
    }
    if (startLat != null && startLon != null) setMarker(startLat, startLon);
    m.on('click', e => setMarker(e.latlng.lat, e.latlng.lng));
    return { map: m, setMarker };
  }

  async function geocodeInto(addrStr, latEl, lonEl, pickerObj=null) {
    try {
      const url = `https://nominatim.openstreetmap.org/search?format=json&limit=1&q=${encodeURIComponent(addrStr)}`;
      const res = await fetch(url); const data = await res.json();
      if (Array.isArray(data) && data.length) {
        const lat = parseFloat(data[0].lat), lon = parseFloat(data[0].lon);
        latEl.value = lat.toFixed(6); lonEl.value = lon.toFixed(6);
        if (pickerObj) { pickerObj.setMarker(lat, lon); pickerObj.map.setView([lat, lon], 12); }
      } else { alert('Could not geocode that address. Try adjusting it or set the pin manually.'); }
    } catch(e) { alert('Geocoding error. Try again.'); }
  }

  const newModal = document.getElementById('newLocationModal');
  let newPicker = null;
  if (newModal) {
    newModal.addEventListener('shown.bs.modal', () => {
      if (!newPicker) {
        newPicker = initPicker('newloc-map', document.getElementById('new-lat'), document.getElementById('new-lon'));
      } else { newPicker.map.invalidateSize(); }
    });
    const geoNewBtn = document.getElementById('geocode-new');
    if (geoNewBtn) {
      geoNewBtn.addEventListener('click', () => geocodeInto(
        document.getElementById('addr-input').value,
        document.getElementById('new-lat'),
        document.getElementById('new-lon'),
        newPicker
      ));
    }
  }

  $$('[id^="editTrip"]').forEach(modal => {
    let picker = null;
    modal.addEventListener('shown.bs.modal', () => {
      const id = modal.id.replace('editTrip', '');
      const latEl = document.getElementById('lat-edit-' + id);
      const lonEl = document.getElementById('lon-edit-' + id);
      const lat = parseFloat(latEl.value); const lon = parseFloat(lonEl.value);
      if (!picker) {
        picker = initPicker('picker-' + id, latEl, lonEl, isFinite(lat)?lat:null, isFinite(lon)?lon:null);
      } else { picker.map.invalidateSize(); }
      const btn = modal.querySelector('button[data-geocode]');
      if (btn && !btn._wired) {
        btn.addEventListener('click', () => {
          const addrSel = btn.getAttribute('data-geocode');
          geocodeInto(modal.querySelector(addrSel).value, latEl, lonEl, picker);
        });
        btn._wired = true;
      }
    });
  });

  // ---------- Collapsible gallery toggle ----------
  document.addEventListener('click', (e) => {
    const btn = e.target.closest('.gallery-toggle');
    if (!btn) return;
    const target = btn.getAttribute('data-target');
    const wrap = document.querySelector(target);
    if (!wrap) return;

    const isCollapsed = wrap.classList.toggle('collapsed'); // toggles and returns new state (true if now collapsed)
    // we actually want "expanded?" so invert:
    const expanded = !isCollapsed;

    btn.setAttribute('aria-expanded', String(expanded));
    const collapsedText = btn.getAttribute('data-collapsed-text') || 'Show all photos';
    const expandedText  = btn.getAttribute('data-expanded-text')  || 'Show less';
    btn.textContent = expanded ? expandedText : collapsedText;

    if (!expanded) {
      // collapsed again — keep comments in view
      btn.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
  });
})();

