import 'dotenv/config';
import express          from 'express';
import Anthropic        from '@anthropic-ai/sdk';
import { getCameras, getActive, getCamera, setActive, getActiveId } from './lib/cameras.js';
import { cgi }          from './lib/cgi.js';
import { visca }        from './lib/visca.js';
import { handlers, tools, clearAllTimers, cancelActiveSequence } from './lib/tools.js';
import { startWatch, stopWatch, addSSEClient, isWatching } from './lib/watch.js';
import { getStream, stopAllStreams } from './lib/streams.js';

const app       = express();
const PORT      = process.env.PORT || 3000;
const USE_VISCA = (process.env.CONTROL_PROTOCOL || 'visca').toLowerCase() === 'visca';

app.use(express.json());
app.use(express.static('public'));

const anthropic = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });

// ── System prompt ─────────────────────────────────────────────────────────────
const SYSTEM_PROMPT = `You control PTZ cameras via VISCA-over-IP and HTTP-CGI commands.

## Active camera
Commands target the currently active camera. Use switch_camera to change it.
Cameras: 1 = 192.168.100.86, 2 = 192.168.100.87, 3 = 192.168.100.88

## Coordinate system & speed ranges
- Pan: left/right, speed 1–24 (slow≈4, medium≈12, fast≈20)
- Tilt: up/down, speed 1–20 (slow≈3, medium≈10, fast≈16)
- Diagonal: leftup, rightup, leftdown, rightdown
- Zoom: in/out, speed 1–7

## Single moves
Use pan_tilt() for any single-direction move. Always set duration_ms.

## Multi-step sequences (circles, scans, sweeps, etc.)
Use execute_sequence() — plan ALL segments at once in one tool call.
The backend executes the full array locally with no model round-trips between segments.
Each segment immediately overrides the current direction — no jerk, no pause between segments.
A final stop is sent automatically after the last segment.

Circle example (8 segments, tune speed/duration to taste):
  direction sequence: right → rightdown → down → leftdown → left → leftup → up → rightup
  Use consistent pan_speed and tilt_speed across all segments for smooth circular motion.
  For a slow circle: pan_speed=6, tilt_speed=4, duration_ms=800 per segment.
  For a fast circle: pan_speed=14, tilt_speed=8, duration_ms=400 per segment.

Only use pan_tilt() + delay() for simple two-step things (e.g. "pan left then right once").
For anything with 3+ direction changes, always use execute_sequence().

## Auto-tracking
"Follow me" / "track me" → toggle_autotrack(enabled=true). Explain that you're
handing off to the camera's onboard tracking system.

## Response style
Be concise. For execute_sequence, list the number of segments and describe the pattern briefly.`;

// ── Emergency stop (fires all protocols, cancels sequences) ───────────────────
async function emergencyStop() {
  cancelActiveSequence();
  stopWatch('emergency stop');
  clearAllTimers();
  const cam = getActive();
  const ops = [cgi.stop(cam.ip)];
  if (USE_VISCA) ops.push(visca.stop(cam.ip), visca.zoom_stop(cam.ip), visca.focus_stop(cam.ip));
  await Promise.allSettled(ops);
}

// ── Agentic chat loop ─────────────────────────────────────────────────────────
async function runChat(messages) {
  const commandLog = [];
  let apiMessages = messages.map(({ role, content }) => ({ role, content }));
  let finalText = '';

  while (true) {
    const response = await anthropic.messages.create({
      model: 'claude-sonnet-4-6',
      max_tokens: 1024,
      system: SYSTEM_PROMPT,
      tools,
      messages: apiMessages,
    });

    for (const b of response.content) {
      if (b.type === 'text') finalText = b.text;
    }

    if (response.stop_reason !== 'tool_use') break;

    const calls   = response.content.filter(b => b.type === 'tool_use');
    const results = [];

    for (const call of calls) {
      const t0 = Date.now();
      let result;
      try {
        result = await handlers[call.name](call.input);
        commandLog.push({ ts: new Date().toISOString(), tool: call.name, input: call.input, result, ms: Date.now()-t0, ok: true, source: 'chat' });
      } catch (err) {
        result = { error: err.message };
        commandLog.push({ ts: new Date().toISOString(), tool: call.name, input: call.input, error: err.message, ms: Date.now()-t0, ok: false, source: 'chat' });
      }
      results.push({ type: 'tool_result', tool_use_id: call.id, content: JSON.stringify(result) });
    }

    apiMessages = [...apiMessages, { role: 'assistant', content: response.content }, { role: 'user', content: results }];
  }

  return { text: finalText, commandLog };
}

// ── Routes ────────────────────────────────────────────────────────────────────

// Chat
app.post('/api/chat', async (req, res) => {
  try {
    res.json(await runChat(req.body.messages));
  } catch (err) {
    console.error('Chat error:', err);
    res.status(500).json({ error: err.message, commandLog: [] });
  }
});

// Emergency stop
app.post('/api/stop', async (req, res) => {
  try {
    await emergencyStop();
    res.json({ ok: true });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

// Manual direct command (bypasses Claude)
app.post('/api/manual', async (req, res) => {
  const { tool, params } = req.body;
  if (!handlers[tool]) return res.status(400).json({ error: `Unknown tool: ${tool}` });
  const t0 = Date.now();
  try {
    const result = await handlers[tool](params || {});
    res.json({ ok: true, tool, result, ms: Date.now()-t0, source: 'manual' });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message, ms: Date.now()-t0 });
  }
});

// Camera list + active state
app.get('/api/cameras', (req, res) => {
  res.json({ cameras: getCameras(), activeId: getActiveId() });
});

app.post('/api/cameras/active', (req, res) => {
  const { id } = req.body;
  if (!setActive(id)) return res.status(400).json({ error: `Invalid camera ID: ${id}` });
  res.json({ ok: true, camera: getActive() });
});

// ── Persistent MJPEG stream endpoint ─────────────────────────────────────────
// The frontend <img> tag points directly here — no JavaScript polling needed.
// Waits up to 6s for the first frame; returns 503 if camera is offline.
app.get('/api/cameras/:id/stream', (req, res) => {
  const cam = getCamera(parseInt(req.params.id));
  if (!cam) return res.status(404).end();

  const stream = getStream(cam.ip);
  let headersSent = false;

  // Deadline: if no frame arrives within 6s the camera is likely offline
  const deadline = setTimeout(() => {
    if (!headersSent && !res.headersSent) {
      unsub();
      res.status(503).json({ error: `${cam.name} (${cam.ip}) not reachable` });
    }
  }, 6000);

  function sendFrame(frame) {
    if (res.writableEnded) { unsub(); return; }
    if (!headersSent) {
      clearTimeout(deadline);
      headersSent = true;
      res.writeHead(200, {
        'Content-Type':  'multipart/x-mixed-replace; boundary=frame',
        'Cache-Control': 'no-cache, no-store',
        'Connection':    'keep-alive',
      });
    }
    try {
      res.write('--frame\r\n');
      res.write(`Content-Type: image/jpeg\r\nContent-Length: ${frame.length}\r\n\r\n`);
      res.write(frame);
      res.write('\r\n');
    } catch (_) { unsub(); }
  }

  // If we already have a cached frame, push it immediately (no 6s wait)
  if (stream.latestFrame) sendFrame(stream.latestFrame);

  const unsub = stream.addListener(sendFrame);
  req.on('close', () => { clearTimeout(deadline); unsub(); });
  req.on('error', () => { clearTimeout(deadline); unsub(); });
});

// ── Gamepad / Volunteer Control endpoints ─────────────────────────────────────
// Target cameras by IP directly — never touches the active-camera state used by chat/manual.
const gpCl = (v, lo, hi) => Math.max(lo, Math.min(hi, Math.round(v)));

app.post('/api/gamepad/command', async (req, res) => {
  const { ip, tool, params = {} } = req.body;
  if (!ip) return res.status(400).json({ error: 'ip required' });
  try {
    let result = { ok: true };
    switch (tool) {
      case 'pan_tilt': {
        const { direction, pan_speed = 12, tilt_speed = 10 } = params;
        const ps = gpCl(pan_speed, 1, 24), ts = gpCl(tilt_speed, 1, 20);
        result = USE_VISCA
          ? await visca.pan_tilt(ip, direction, ps, ts)
          : await cgi.pan_tilt(ip, direction, ps, ts);
        break;
      }
      case 'pan_tilt_stop':
        result = USE_VISCA ? await visca.stop(ip) : await cgi.stop(ip);
        break;
      case 'zoom': {
        const { direction, speed = 3 } = params;
        const s = gpCl(speed, 1, 7);
        result = USE_VISCA
          ? await visca.zoom(ip, direction, s)
          : await cgi.zoom(ip, direction === 'in' ? 'zoomin' : 'zoomout', s);
        break;
      }
      case 'zoom_stop':
        result = USE_VISCA ? await visca.zoom_stop(ip) : await cgi.zoom_stop(ip);
        break;
      case 'focus': {
        const { direction, speed = 3 } = params;
        const s = gpCl(speed, 1, 7);
        result = USE_VISCA
          ? await visca.focus(ip, direction, s)
          : await cgi.focus(ip, direction === 'near' ? 'focusin' : 'focusout', s);
        break;
      }
      case 'focus_stop':
        result = USE_VISCA ? await visca.focus_stop(ip) : await cgi.focus_stop(ip);
        break;
      case 'focus_mode': {
        const { mode } = params; // 'auto' or 'manual'
        result = USE_VISCA ? await visca.focus_mode(ip, mode) : await cgi.focus_mode(ip, mode);
        break;
      }
      case 'autotrack': {
        const { enabled } = params;
        result = await cgi.autotrack(ip, enabled); // CGI only — no VISCA equivalent
        break;
      }
      default:
        return res.status(400).json({ error: `Unknown gamepad tool: ${tool}` });
    }
    res.json({ ok: true, result });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

app.post('/api/gamepad/stop-all', async (req, res) => {
  const ops = getCameras().flatMap(cam => USE_VISCA
    ? [visca.stop(cam.ip), visca.zoom_stop(cam.ip), visca.focus_stop(cam.ip)]
    : [cgi.stop(cam.ip)]
  );
  await Promise.allSettled(ops);
  res.json({ ok: true });
});

// Watch Mode SSE stream
app.get('/api/watch/events', (req, res) => {
  res.writeHead(200, {
    'Content-Type':  'text/event-stream',
    'Cache-Control': 'no-cache',
    'Connection':    'keep-alive',
  });
  res.write(`data: ${JSON.stringify({ event: 'connected' })}\n\n`);
  addSSEClient(res);
});

app.post('/api/watch/start', async (req, res) => {
  const { instruction } = req.body;
  if (!instruction?.trim()) return res.status(400).json({ error: 'instruction required' });
  res.json(await startWatch(instruction.trim(), handlers));
});

app.post('/api/watch/stop', (req, res) => {
  stopWatch('user stopped watch mode');
  res.json({ ok: true });
});

app.get('/api/watch/status', (req, res) => {
  res.json({ watching: isWatching() });
});

// ── Start ─────────────────────────────────────────────────────────────────────
process.on('SIGTERM', () => { stopAllStreams(); process.exit(0); });
process.on('SIGINT',  () => { stopAllStreams(); process.exit(0); });

app.listen(PORT, () => {
  const cam = getActive();
  console.log(`\n🎥 PTZ AI Controller  →  http://localhost:${PORT}`);
  console.log(`📡 Active camera      →  ${cam.name} (${cam.ip})`);
  console.log(`🎛️  Control protocol   →  ${USE_VISCA ? `VISCA-over-IP (port ${process.env.VISCA_PORT || 1259})` : 'HTTP-CGI'}`);
  console.log(`📷 Cameras            →  ${getCameras().map(c => `${c.name} @ ${c.ip}`).join(', ')}\n`);
});
