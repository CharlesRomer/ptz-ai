/* Screen 3: stream health <-> startup checklist, big toggle button. */
(function () {
  const streamView = document.getElementById('view-stream');
  const checkView = document.getElementById('view-checklist');
  const toggleBtn = document.getElementById('toggle');
  let mode = localStorage.getItem('screen3mode') || 'stream';
  const bitrateHistory = []; // [t_ms, kbps], ~5 minutes
  let lastState = null;

  function setMode(m) {
    mode = m;
    localStorage.setItem('screen3mode', m);
    streamView.style.display = m === 'stream' ? 'block' : 'none';
    checkView.style.display = m === 'checklist' ? 'block' : 'none';
    toggleBtn.textContent = m === 'stream' ? '📋 Checklist' : '📈 Stream health';
    if (lastState) render(lastState);
  }
  toggleBtn.onclick = function () { setMode(mode === 'stream' ? 'checklist' : 'stream'); };

  /* ---------- stream view ---------- */
  function renderStream(s) {
    const obs = s.obs || {};
    const st = obs.stream || {};
    const stats = obs.stats || {};
    const yt = s.youtube;
    const atem = s.atem || {};

    setBadge('b-live', st.active,
      st.active ? '● LIVE' : 'OFFLINE', st.active ? 'on' : 'off');
    if (st.reconnecting) setBadge('b-live', true, '⟳ RECONNECTING', 'warn');
    setBadge('b-rec', (obs.record || {}).active,
      (obs.record || {}).active ? '● REC' : 'REC off',
      (obs.record || {}).active ? 'ok' : 'off');
    const ytEl = document.getElementById('b-yt');
    if (yt) {
      ytEl.style.display = '';
      setBadge('b-yt', yt.live, yt.live ? 'YouTube ✓' : 'YouTube ?',
        yt.live ? 'ok' : 'warn');
    } else { ytEl.style.display = 'none'; }

    stat('s-time', st.timecode || '00:00:00', '');
    stat('s-kbps', st.kbps != null ? st.kbps : '—',
      st.kbps != null && st.kbps < 2000 && st.active ? 'warn' : '');
    stat('s-drop', (st.dropped_pct != null ? st.dropped_pct : '—') + '%',
      st.dropped_pct > 2 ? 'error' : st.dropped_pct > 0.5 ? 'warn' : '');
    stat('s-cpu', (stats.cpu_pct != null ? stats.cpu_pct : '—') + '%',
      stats.cpu_pct > 80 ? 'error' : stats.cpu_pct > 60 ? 'warn' : '');
    stat('s-fps', stats.fps != null ? stats.fps : '—', '');
    stat('s-lag', (stats.render_skip_pct != null ? stats.render_skip_pct : '—') + '%',
      stats.render_skip_pct > 2 ? 'error' : '');

    const ytLine = document.getElementById('ytline');
    ytLine.textContent = yt ? (yt.message || '') :
      'YouTube API check not configured (optional)';
    document.getElementById('obsline').textContent = obs.message || 'Waiting for OBS…';
    document.getElementById('atemline').textContent =
      'ATEM: ' + (atem.message || 'no data');

    if (st.active && st.kbps != null) {
      bitrateHistory.push([Date.now(), st.kbps]);
      while (bitrateHistory.length && Date.now() - bitrateHistory[0][0] > 300000)
        bitrateHistory.shift();
    }
    drawSpark();
  }

  function setBadge(id, on, text, cls) {
    const el = document.getElementById(id);
    el.textContent = text;
    el.className = 'badge ' + cls;
  }
  function stat(id, value, cls) {
    const el = document.getElementById(id);
    el.textContent = value;
    el.className = 'v ' + cls;
  }

  function drawSpark() {
    const cv = document.getElementById('spark');
    const ctx = cv.getContext('2d');
    cv.width = cv.clientWidth; cv.height = cv.clientHeight;
    ctx.clearRect(0, 0, cv.width, cv.height);
    if (bitrateHistory.length < 2) return;
    const max = Math.max.apply(null, bitrateHistory.map(function (p) { return p[1]; })) * 1.15;
    const t0 = bitrateHistory[0][0];
    const span = Math.max(bitrateHistory[bitrateHistory.length - 1][0] - t0, 1);
    ctx.strokeStyle = '#1db954'; ctx.lineWidth = 2; ctx.beginPath();
    bitrateHistory.forEach(function (p, i) {
      const x = ((p[0] - t0) / span) * (cv.width - 8) + 4;
      const y = cv.height - 4 - (p[1] / max) * (cv.height - 8);
      i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
    });
    ctx.stroke();
    ctx.fillStyle = '#9aa0a6'; ctx.font = '12px system-ui';
    ctx.fillText('bitrate, last 5 min', 8, 14);
  }

  /* ---------- checklist view ---------- */
  function post(action) {
    fetch('/api/checklist/' + action, { method: 'POST' }).catch(function () {});
  }

  function renderChecklist(s) {
    const ck = s.checklist || {};
    const steps = ck.steps || [];
    const dots = steps.map(function (st) {
      return '<div class="dot' + (st.done ? ' done' : st.current ? ' current' : '') + '"></div>';
    }).join('');
    document.getElementById('ck-progress').innerHTML = dots;

    const body = document.getElementById('ck-body');
    if (ck.complete) {
      body.innerHTML =
        '<div class="ck-done"><h2>✅ All done — you\'re ready!</h2>' +
        '<div class="ck-buttons"><button onclick="RackCk.reset()">Start over</button></div></div>';
      return;
    }
    const cur = steps.filter(function (st) { return st.current; })[0];
    if (!cur) { body.innerHTML = ''; return; }
    let chip = '';
    if (cur.auto) {
      chip = cur.auto_ok
        ? '<div class="chip pass">✓ Detected automatically — looks good</div>'
        : '<div class="chip">… waiting for this to show up on the system</div>';
    }
    body.innerHTML =
      '<div class="ck-step"><h2>Step ' + (ck.current + 1) + ' of ' + ck.total +
      ': ' + esc(cur.title) + '</h2>' +
      (cur.detail ? '<p>' + esc(cur.detail) + '</p>' : '') + chip + '</div>' +
      '<div class="ck-buttons">' +
      '<button onclick="RackCk.back()"' + (ck.current === 0 ? ' disabled' : '') + '>‹ Back</button>' +
      '<button class="primary" onclick="RackCk.advance()">Done, next ›</button>' +
      '<button onclick="RackCk.reset()">Reset</button></div>';
  }

  window.RackCk = {
    advance: function () { post('advance'); },
    back: function () { post('back'); },
    reset: function () {
      if (confirm('Reset the checklist back to step 1?')) post('reset');
    }
  };

  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }

  function render(s) {
    lastState = s;
    if (mode === 'stream') renderStream(s); else renderChecklist(s);
  }

  setMode(mode);
  RackBus.startClock();
  RackBus.connect(render);
})();
