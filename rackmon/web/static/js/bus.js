/* Shared WebSocket state bus with auto-reconnect + offline banner. */
(function () {
  let retry = 1000;
  let banner = null;

  function ensureBanner() {
    if (!banner) {
      banner = document.createElement('div');
      banner.className = 'offline-banner';
      banner.textContent = 'BACKEND OFFLINE — reconnecting…';
      banner.style.display = 'none';
      document.body.appendChild(banner);
    }
    return banner;
  }

  function connect(onState) {
    const ws = new WebSocket('ws://' + location.host + '/ws');
    ws.onopen = function () {
      retry = 1000;
      ensureBanner().style.display = 'none';
    };
    ws.onmessage = function (e) {
      try { onState(JSON.parse(e.data)); } catch (err) { console.error(err); }
    };
    ws.onclose = function () {
      ensureBanner().style.display = 'block';
      setTimeout(function () { connect(onState); }, retry);
      retry = Math.min(retry * 1.5, 10000);
    };
    ws.onerror = function () { ws.close(); };
  }

  function startClock() {
    const el = document.getElementById('clock');
    if (!el) return;
    setInterval(function () {
      el.textContent = new Date().toLocaleTimeString([], {
        hour: '2-digit', minute: '2-digit', second: '2-digit'
      });
    }, 1000);
  }

  window.RackBus = { connect: connect, startClock: startClock };
})();
