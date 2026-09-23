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
        '<div class="ctl" id="ctl-' + c.id + '" style="display:none">' +
          '<span class="ctl-dot" id="ctldot-' + c.id + '"></span>' +
          '<span class="ctl-pad" id="ctlpad-' + c.id + '"></span>' +
          ['pan', 'tilt', 'zoom'].map(function (axis) {
            return '<div class="ctl-row"><span>' + axis[0].toUpperCase() + '</span>' +
              '<div class="ctl-bar"><div class="ctl-fill" id="ctl-' + axis + '-' + c.id +
              '"></div></div></div>';
          }).join('') +
        '</div>' +
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

      updateControlOverlay(c.id, ((s.control || {}).cameras || {})[c.id]);
    });
  }

  function setBar(id, value) {
    var fill = document.getElementById(id);
    if (!fill) return;
    var pct = Math.min(Math.abs(value || 0), 1) * 50;
    fill.style.width = pct + '%';
    fill.style.left = value < 0 ? (50 - pct) + '%' : '50%';
    fill.classList.toggle('on', Math.abs(value || 0) > 0.01);
  }

  function updateControlOverlay(camId, ctl) {
    var box = document.getElementById('ctl-' + camId);
    if (!box) return;
    if (!ctl) { box.style.display = 'none'; return; }
    box.style.display = 'flex';
    var dot = document.getElementById('ctldot-' + camId);
    dot.className = 'ctl-dot ' + (ctl.connected ? 'on' : 'off');
    dot.title = 'Controller ' + ctl.controller;
    document.getElementById('ctlpad-' + camId).textContent = '🎮' + ctl.controller;
    box.classList.toggle('active', !!ctl.moving);
    setBar('ctl-pan-' + camId, ctl.pan);
    setBar('ctl-tilt-' + camId, ctl.tilt);
    setBar('ctl-zoom-' + camId, ctl.zoom);
  }

  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }

  RackBus.connect(render);
})();
