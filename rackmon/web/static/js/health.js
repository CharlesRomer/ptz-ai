/* Screen 1: system health board — green/red tiles per device. */
(function () {
  const tilesEl = document.getElementById('tiles');
  const overallEl = document.getElementById('overall');

  function tile(status, name, detail) {
    return { status: status || 'unknown', name: name, detail: detail || '' };
  }

  function buildTiles(s) {
    const tiles = [];

    // ATEM
    const atem = s.atem || {};
    let atemDetail = atem.message || '';
    if (atem.connected) {
      const parts = [atem.model || 'connected'];
      if (atem.streaming !== null && atem.streaming !== undefined)
        parts.push(atem.streaming ? 'ATEM streaming' : 'ATEM stream off');
      if (atem.recording !== null && atem.recording !== undefined)
        parts.push(atem.recording ? 'ISO recording' : 'not recording');
      atemDetail = parts.join(' · ');
    }
    tiles.push(tile(atem.status, 'ATEM Switcher', atemDetail));

    // OBS
    const obs = s.obs || {};
    tiles.push(tile(obs.status, 'OBS (encoder)', obs.message || ''));

    // Mini PC
    const sys = s.system || {};
    let sysDetail = sys.message || '';
    if (sys.disks && sys.disks.length) {
      sysDetail += '\n' + sys.disks.map(function (d) {
        return d.pct === null ? (d.path + ': ?') : (d.path + ' ' + d.pct + '% used');
      }).join(' · ');
    }
    tiles.push(tile(sys.status, 'Mini PC', sysDetail));

    // PoE switch ports (tile omitted entirely when SNMP isn't configured)
    const sw = s.switch;
    if (sw && sw.ports && sw.ports.length && !sw.stale) {
      sw.ports.forEach(function (p) {
        tiles.push(tile(p.ok ? 'ok' : 'error',
          'Port ' + p.port + ' — ' + p.label, p.detail));
      });
      if (sw.status !== 'ok') {
        tiles.push(tile(sw.status, 'PoE Switch', sw.message || ''));
      }
    } else if (sw) {
      tiles.push(tile(sw.status, 'PoE Switch', sw.message || 'no data'));
    }

    // Ping targets (WiFi extender, router, ...)
    const ping = s.ping || {};
    (ping.targets || []).forEach(function (t) {
      tiles.push(tile(t.ok ? 'ok' : 'error', t.label,
        t.ok ? ('reachable · ' + t.rtt_ms + ' ms') : 'UNREACHABLE'));
    });

    // YouTube (only when configured)
    if (s.youtube) {
      tiles.push(tile(s.youtube.status, 'YouTube', s.youtube.message || ''));
    }
    return tiles;
  }

  function render(s) {
    const tiles = buildTiles(s);
    tilesEl.innerHTML = tiles.map(function (t) {
      return '<div class="tile ' + t.status + '">' +
        '<div class="tile-name">' + esc(t.name) + '</div>' +
        '<div class="tile-detail">' + esc(t.detail).replace(/\n/g, '<br>') + '</div></div>';
    }).join('');

    const errors = tiles.filter(function (t) { return t.status === 'error'; }).length;
    const warns = tiles.filter(function (t) { return t.status === 'warn'; }).length;
    if (errors) {
      overallEl.className = 'error';
      overallEl.textContent = errors + ' PROBLEM' + (errors > 1 ? 'S' : '');
    } else if (warns) {
      overallEl.className = 'warn';
      overallEl.textContent = 'CHECK ' + warns + ' ITEM' + (warns > 1 ? 'S' : '');
    } else {
      overallEl.className = 'ok';
      overallEl.textContent = 'ALL SYSTEMS GO';
    }
  }

  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }

  RackBus.startClock();
  RackBus.connect(render);
})();
