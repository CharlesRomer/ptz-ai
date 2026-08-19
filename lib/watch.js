// Watch Mode — vision loop: grab frame → Claude with image → execute tool calls → repeat
import Anthropic     from '@anthropic-ai/sdk';
import { getActive } from './cameras.js';
import { getStream } from './streams.js';

const anthropic    = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });
const MAX_WATCH_MS  = 10 * 60 * 1000; // 10-minute hard timeout
const CYCLE_GAP_MS  = 500;            // gap after cycle completes; AI call is the natural throttle
const MAX_ROUNDS    = 3;              // max Claude round-trips per frame (caps per-cycle latency)

// ── SSE clients ──────────────────────────────────────────────────────────────
const clients = new Set();

export function addSSEClient(res) {
  clients.add(res);
  res.on('close', () => clients.delete(res));
}

function broadcast(payload) {
  const msg = `data: ${JSON.stringify(payload)}\n\n`;
  for (const c of clients) {
    try { c.write(msg); } catch (_) { clients.delete(c); }
  }
}

// ── State ────────────────────────────────────────────────────────────────────
let state = { running: false, instruction: '', timeoutId: null };

export const isWatching = () => state.running;

export async function startWatch(instruction, handlers) {
  if (state.running) return { error: 'Already in watch mode' };
  state = { running: true, instruction, timeoutId: null };
  state.timeoutId = setTimeout(
    () => stopWatch('10-minute auto-timeout — re-enable to continue'),
    MAX_WATCH_MS,
  );
  runLoop(handlers).catch(err => {
    broadcast({ event: 'error', message: err.message });
    stopWatch('loop error');
  });
  return { ok: true };
}

export function stopWatch(reason = 'user request') {
  if (!state.running) return;
  state.running = false;
  if (state.timeoutId) { clearTimeout(state.timeoutId); state.timeoutId = null; }
  broadcast({ event: 'stopped', reason });
}

// ── Watch Mode tool subset (tighter limits than chat mode) ───────────────────
const WATCH_TOOLS = [
  {
    name: 'report_reasoning',
    description: 'ALWAYS call this first. One sentence (≤120 chars): what you observe and what you will do.',
    input_schema: {
      type: 'object',
      properties: { reasoning: { type: 'string', maxLength: 120 } },
      required: ['reasoning'],
    },
  },
  {
    name: 'pan_tilt',
    description: 'Move camera. Keep duration_ms ≤1500 in watch mode. Use slow speeds for smooth tracking.',
    input_schema: {
      type: 'object',
      properties: {
        direction:   { type: 'string', enum: ['left','right','up','down','leftup','rightup','leftdown','rightdown'] },
        pan_speed:   { type: 'integer', minimum: 1, maximum: 16, description: 'Keep low (3-8) for smooth tracking.' },
        tilt_speed:  { type: 'integer', minimum: 1, maximum: 12 },
        duration_ms: { type: 'integer', minimum: 100, maximum: 1500 },
      },
      required: ['direction', 'duration_ms'],
    },
  },
  {
    name: 'stop',
    description: 'Stop all movement.',
    input_schema: { type: 'object', properties: {} },
  },
  {
    name: 'zoom',
    description: 'Zoom in or out. Keep gentle in watch mode.',
    input_schema: {
      type: 'object',
      properties: {
        direction:   { type: 'string', enum: ['in','out','stop'] },
        speed:       { type: 'integer', minimum: 1, maximum: 4 },
        duration_ms: { type: 'integer', minimum: 100, maximum: 1500 },
      },
      required: ['direction', 'duration_ms'],
    },
  },
];

// ── Watch loop ───────────────────────────────────────────────────────────────
async function runLoop(handlers) {
  const recentReasons = [];

  while (state.running) {
    const cam = getActive();
    broadcast({ event: 'cycle_start', ts: new Date().toISOString(), camera: cam.name });

    // Pull latest frame from the persistent MJPEG stream (fast — no new connection)
    let frame;
    try {
      frame = await getStream(cam.ip).getFrameB64();
    } catch (err) {
      broadcast({ event: 'error', message: `Frame grab failed: ${err.message}` });
      await sleep(CYCLE_GAP_MS);
      continue;
    }

    if (!state.running) break;

    // Build per-cycle system prompt with current instruction embedded
    const systemPrompt =
      `You are controlling a PTZ camera in Watch Mode. Follow the user's instruction precisely.\n\n` +
      `Instruction: "${state.instruction}"\n\n` +
      `Speed guide: pan 1-16 (use 3-6 for small corrections, 8-12 for large ones), ` +
      `tilt 1-12, zoom 1-4. Max duration_ms 1500. Keep movements small and smooth — ` +
      `overcorrecting causes oscillation. If the subject is already well-centered, ` +
      `call stop() or do nothing.\n\n` +
      `ALWAYS call report_reasoning first (1 sentence, ≤120 chars).\n` +
      `Recent actions: ${recentReasons.slice(-3).join(' | ') || 'none'}`;

    try {
      // Mini agentic loop: feed tool results back to Claude so it can chain calls.
      // Root cause of the "reasoning logs but no movement" bug: without this loop,
      // Claude calls report_reasoning, we log it, but never send the tool result back.
      // Claude was waiting for the result before deciding to call pan_tilt — it never got it.
      let apiMessages = [{
        role: 'user',
        content: [
          { type: 'image', source: { type: 'base64', media_type: 'image/jpeg', data: frame } },
          { type: 'text',  text: 'Analyze frame and adjust camera. Call report_reasoning first, then immediately call any camera tool(s) needed.' },
        ],
      }];

      for (let round = 0; round < MAX_ROUNDS && state.running; round++) {
        const response = await anthropic.messages.create({
          model: 'claude-sonnet-4-6',
          max_tokens: 512,
          system: systemPrompt,
          tools: WATCH_TOOLS,
          messages: apiMessages,
        });

        if (response.stop_reason !== 'tool_use') break; // Claude is done

        const calls = response.content.filter(b => b.type === 'tool_use');
        const toolResults = [];

        for (const call of calls) {
          if (!state.running) break;

          if (call.name === 'report_reasoning') {
            const text = (call.input.reasoning || '').slice(0, 120);
            recentReasons.push(text);
            if (recentReasons.length > 10) recentReasons.shift();
            broadcast({ event: 'reasoning', ts: new Date().toISOString(), text });
            // Return the tool result so Claude can proceed to call camera tools
            toolResults.push({ type: 'tool_result', tool_use_id: call.id, content: 'logged' });
            continue;
          }

          const t0 = Date.now();
          try {
            const result = await handlers[call.name](call.input);
            broadcast({ event: 'command', entry: {
              ts: new Date().toISOString(), tool: call.name, input: call.input,
              result, ms: Date.now()-t0, ok: true, source: 'watch',
            }});
            toolResults.push({ type: 'tool_result', tool_use_id: call.id, content: JSON.stringify(result) });
          } catch (err) {
            broadcast({ event: 'command', entry: {
              ts: new Date().toISOString(), tool: call.name, input: call.input,
              error: err.message, ms: Date.now()-t0, ok: false, source: 'watch',
            }});
            toolResults.push({ type: 'tool_result', tool_use_id: call.id, content: JSON.stringify({ error: err.message }) });
          }
        }

        // Feed results back for the next round
        apiMessages = [
          ...apiMessages,
          { role: 'assistant', content: response.content },
          { role: 'user',      content: toolResults },
        ];
      }
    } catch (err) {
      broadcast({ event: 'error', message: `Claude error: ${err.message}` });
    }

    if (state.running) await sleep(CYCLE_GAP_MS);
  }
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
