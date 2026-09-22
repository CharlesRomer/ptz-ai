/* Screen 2: tally multiview — camera grid with red PGM / green PVW borders. */
(function () {
  const grid = document.getElementById('mvgrid');
  const banner = document.getElementById('tallybanner');
  let cams = null;          // from meta.cameras
  let staleAfter = 10;
  const FRAME_MS = 250;     // ~4 fps refresh per tile

  function buildGrid(cameras) {
    cams = cameras;
    const n = cameras.length || 1;
    const cols = n <= 2 ? n : n <= 4 ? 2 : n <= 6 ? 3 : n <= 9 ? 3 : 4;
    grid.style.gridTemplateColumns = 'repeat(' + cols + ', 1fr)';
    grid.innerHTML = cameras.map(function (c) {
      return '<div class="cam" id="cam-' + c.id + '">' +
        '<img id="img-' + c.id + '" alt="">' +
        '<div class="nosignal">NO SIGNAL</div>' +
        '<div class="cam-label">' + esc(c.label) + '</div></div>';
    }).join('');
    cameras.forEach(function (c) {
      let busy = false;
      setInterval(function () {
        if (busy || document.hidden) return;
        busy = true;
        fetch('/api/frame/' + encodeURIComponent(c.id), { cache: 'no-store' })
          .then(function (r) { return r.ok ? r.blob() : null; })
          .then(function (blob) {
            if (!blob) return;
            const img = document.getElementById('img-' + c.id);
            const old = img.src;
            img.src = URL.createObjectURL(blob);
            if (old && old.startsWith('blob:')) URL.revokeObjectURL(old);
          })
          .catch(function () {})
          .finally(function () { busy = false; });
      }, FRAME_MS);
    });
  }

  function render(s) {
    const meta = s.meta || {};
    if (!cams && meta.cameras) {
      staleAfter = meta.stale_after || 10;
      buildGrid(meta.cameras);
    }
    if (!cams) return;

    const atem = s.atem || {};
    const tallyOk = atem.status === 'ok' && atem.connected;
    banner.style.display = tallyOk ? 'none' : 'block';
    banner.textContent = 'TALLY UNAVAILABLE — ' + (atem.message || 'ATEM offline');

    const frames = s.frames || {};
    cams.forEach(function (c) {
      const el = document.getElementById('cam-' + c.id);
      if (!el) return;
      el.classList.toggle('stale',
        frames[c.id] === undefined || frames[c.id] > staleAfter);
      let live = false, next = false;
      if (tallyOk && c.atem_input !== null && c.atem_input !== undefined) {
        const t = (atem.tally || {})[String(c.atem_input)] || {};
        live = !!t.program || atem.program === c.atem_input;
        next = !live && (!!t.preview || atem.preview === c.atem_input);
      }
      el.classList.toggle('live', live);
      el.classList.toggle('next', next);
    });
  }

  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }

  RackBus.connect(render);
})();
