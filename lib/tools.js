// Tool definitions and handlers — shared between chat mode and watch mode
import { cgi }      from './cgi.js';
import { visca }    from './visca.js';
import { getActive, setActive } from './cameras.js';

const USE_VISCA = (process.env.CONTROL_PROTOCOL || 'visca').toLowerCase() === 'visca';
const MAX_MOVE_MS = Math.min(parseInt(process.env.MAX_MOVE_DURATION_MS) || 5000, 8000);
const cl = (v, lo, hi) => Math.max(lo, Math.min(hi, Math.round(v)));

// ── Sequence state ────────────────────────────────────────────────────────────
// Lets stop() and emergencyStop() cancel a running execute_sequence mid-flight.
let _seqRunning   = false;
let _seqCancelled = false;

export function cancelActiveSequence() {
  if (_seqRunning) _seqCancelled = true;
}

// ── Auto-stop timers ─────────────────────────────────────────────────────────
const timers = new Map();

function autoStop(key, ms, stopFn) {
  if (timers.has(key)) clearTimeout(timers.get(key));
  timers.set(key, setTimeout(async () => {
    await stopFn().catch(() => {});
    timers.delete(key);
  }, ms));
}

export function clearAllTimers() {
  for (const t of timers.values()) clearTimeout(t);
  timers.clear();
}

// ── Movement abstraction: VISCA primary, CGI fallback ────────────────────────
const move = {
  pan_tilt(ip, dir, ps, ts) {
    return USE_VISCA ? visca.pan_tilt(ip, dir, ps, ts) : cgi.pan_tilt(ip, dir, ps, ts);
  },
  async stop(ip) {
    clearAllTimers();
    const ops = USE_VISCA
      ? [visca.stop(ip), visca.zoom_stop(ip), visca.focus_stop(ip), cgi.stop(ip)]
      : [cgi.stop(ip)];
    const results = await Promise.allSettled(ops);
    return results[0].value || { ok: true, status: 200 };
  },
  zoom(ip, dir, s) {
    return USE_VISCA ? visca.zoom(ip, dir, s)
      : cgi.zoom(ip, dir === 'in' ? 'zoomin' : 'zoomout', s);
  },
  zoom_stop(ip) {
    return USE_VISCA ? visca.zoom_stop(ip) : cgi.zoom_stop(ip);
  },
  focus(ip, dir, s) {
    return USE_VISCA ? visca.focus(ip, dir, s)
      : cgi.focus(ip, dir === 'near' ? 'focusin' : 'focusout', s);
  },
  focus_stop(ip) {
    return USE_VISCA ? visca.focus_stop(ip) : cgi.focus_stop(ip);
  },
  focus_mode(ip, mode) {
    return USE_VISCA ? visca.focus_mode(ip, mode) : cgi.focus_mode(ip, mode);
  },
  home(ip) {
    clearAllTimers();
    return USE_VISCA ? visca.home(ip) : cgi.home(ip);
  },
  preset_recall(ip, n) {
    return USE_VISCA ? visca.preset_recall(ip, n) : cgi.preset_recall(ip, n);
  },
  preset_save(ip, n) {
    return USE_VISCA ? visca.preset_save(ip, n) : cgi.preset_save(ip, n);
  },
};

// ── Tool handlers ────────────────────────────────────────────────────────────
export const handlers = {
  async pan_tilt({ direction, pan_speed = 12, tilt_speed = 10, duration_ms = 2000 }) {
    const cam = getActive();
    const ps = cl(pan_speed, 1, 24), ts = cl(tilt_speed, 1, 20), dur = cl(duration_ms, 100, MAX_MOVE_MS);
    const result = await move.pan_tilt(cam.ip, direction, ps, ts);
    autoStop('pan_tilt', dur, () => move.stop(cam.ip));
    return { ...result, direction, pan_speed: ps, tilt_speed: ts, auto_stop_ms: dur };
  },

  async stop() {
    cancelActiveSequence(); // abort any running sequence immediately
    return move.stop(getActive().ip);
  },

  async zoom({ direction, speed = 3, duration_ms = 2000 }) {
    const cam = getActive();
    const s = cl(speed, 1, 7), dur = cl(duration_ms, 100, MAX_MOVE_MS);
    if (direction === 'stop') {
      clearTimeout(timers.get('zoom')); timers.delete('zoom');
      return move.zoom_stop(cam.ip);
    }
    const result = await move.zoom(cam.ip, direction, s);
    autoStop('zoom', dur, () => move.zoom_stop(cam.ip));
    return { ...result, direction, speed: s, auto_stop_ms: dur };
  },

  async focus({ direction, speed = 3, duration_ms = 1500 }) {
    const cam = getActive();
    const s = cl(speed, 1, 7), dur = cl(duration_ms, 100, 5000);
    if (direction === 'stop') {
      clearTimeout(timers.get('focus')); timers.delete('focus');
      return move.focus_stop(cam.ip);
    }
    const result = await move.focus(cam.ip, direction, s);
    autoStop('focus', dur, () => move.focus_stop(cam.ip));
    return { ...result, direction, speed: s, auto_stop_ms: dur };
  },

  async set_focus_mode({ mode }) {
    return move.focus_mode(getActive().ip, mode);
  },

  async go_home() {
    return move.home(getActive().ip);
  },

  async recall_preset({ preset_number }) {
    return move.preset_recall(getActive().ip, cl(preset_number, 0, 254));
  },

  async save_preset({ preset_number }) {
    return move.preset_save(getActive().ip, cl(preset_number, 0, 254));
  },

  async toggle_autotrack({ enabled }) {
    // Hands off to the camera's onboard tracking system.
    // TODO: Future — pull frames from rtsp://CAMERA_IP:554/1, run subject detection
    // (e.g. local YOLO or vision model), compute pan/tilt error, issue corrective
    // pan_tilt calls in a PID control loop instead of relying on onboard tracking.
    return cgi.autotrack(getActive().ip, enabled);
  },

  async set_white_balance({ mode }) {
    return cgi.wb_mode(getActive().ip, mode);
  },

  async set_exposure_mode({ mode }) {
    return cgi.ae_mode(getActive().ip, mode);
  },

  async set_iris({ value }) {
    return cgi.iris(getActive().ip, value);
  },

  async set_shutter({ value }) {
    return cgi.shutter(getActive().ip, value);
  },

  async set_gain({ value }) {
    return cgi.gain(getActive().ip, cl(value, 0, 15));
  },

  async set_rgain({ value }) {
    return cgi.rgain(getActive().ip, cl(value, 0, 255));
  },

  async set_bgain({ value }) {
    return cgi.bgain(getActive().ip, cl(value, 0, 255));
  },

  async set_sharpness({ value }) {
    return cgi.sharpness(getActive().ip, cl(value, 0, 15));
  },

  async switch_camera({ camera_id }) {
    if (!setActive(camera_id)) throw new Error(`Invalid camera ID: ${camera_id}`);
    return { ok: true, active_camera: getActive() };
  },

  async delay({ ms }) {
    const dur = cl(ms, 50, 5000);
    await new Promise(r => setTimeout(r, dur));
    return { delayed_ms: dur };
  },

  async execute_sequence({ segments }) {
    if (_seqRunning) return { error: 'Sequence already running — call stop() first' };
    const cam = getActive();
    _seqRunning   = true;
    _seqCancelled = false;
    const executed = [];

    try {
      for (let i = 0; i < segments.length; i++) {
        if (_seqCancelled) break;

        const { direction, pan_speed = 10, tilt_speed = 8, duration_ms } = segments[i];
        const ps  = cl(pan_speed,  1, 24);
        const ts  = cl(tilt_speed, 1, 20);
        const dur = cl(duration_ms, 100, MAX_MOVE_MS);

        // Issue move — immediately overrides current motion, NO stop between segments.
        // This is what makes sequences smooth: the motor transitions directly without
        // deceleration-stop-acceleration overhead between each direction change.
        await move.pan_tilt(cam.ip, direction, ps, ts);
        executed.push({ i, direction, pan_speed: ps, tilt_speed: ts, duration_ms: dur });

        // Hold this direction for duration_ms then switch to the next segment.
        await new Promise(r => setTimeout(r, dur));
      }
    } finally {
      // Always send a final stop — even if cancelled mid-sequence.
      await move.stop(cam.ip).catch(() => {});
      _seqRunning   = false;
      _seqCancelled = false;
    }

    return {
      ok: true,
      segments_total:    segments.length,
      segments_executed: executed.length,
    };
  },
};

// ── Tool definitions for Claude ──────────────────────────────────────────────
export const tools = [
  {
    name: 'pan_tilt',
    description: 'Move camera in a direction. Always set duration_ms — camera moves continuously until auto-stopped.',
    input_schema: {
      type: 'object',
      properties: {
        direction:   { type: 'string', enum: ['left','right','up','down','leftup','rightup','leftdown','rightdown'] },
        pan_speed:   { type: 'integer', minimum: 1, maximum: 24,  description: 'Default 12. Slow≈4, medium≈12, fast≈20.' },
        tilt_speed:  { type: 'integer', minimum: 1, maximum: 20,  description: 'Default 10. Slow≈3, medium≈10, fast≈16.' },
        duration_ms: { type: 'integer', minimum: 100, maximum: 5000, description: 'Auto-stop after N ms. Always set explicitly.' },
      },
      required: ['direction', 'duration_ms'],
    },
  },
  {
    name: 'stop',
    description: 'Immediately stop all pan, tilt, and zoom movement.',
    input_schema: { type: 'object', properties: {} },
  },
  {
    name: 'zoom',
    description: 'Zoom in, out, or stop zoom.',
    input_schema: {
      type: 'object',
      properties: {
        direction:   { type: 'string', enum: ['in','out','stop'] },
        speed:       { type: 'integer', minimum: 1, maximum: 7, description: 'Default 3.' },
        duration_ms: { type: 'integer', minimum: 100, maximum: 5000 },
      },
      required: ['direction', 'duration_ms'],
    },
  },
  {
    name: 'focus',
    description: 'Adjust focus near/far or stop focus movement.',
    input_schema: {
      type: 'object',
      properties: {
        direction:   { type: 'string', enum: ['near','far','stop'] },
        speed:       { type: 'integer', minimum: 1, maximum: 7 },
        duration_ms: { type: 'integer', minimum: 100, maximum: 3000 },
      },
      required: ['direction', 'duration_ms'],
    },
  },
  {
    name: 'set_focus_mode',
    description: 'Switch between auto and manual focus.',
    input_schema: {
      type: 'object',
      properties: { mode: { type: 'string', enum: ['auto','manual'] } },
      required: ['mode'],
    },
  },
  {
    name: 'go_home',
    description: 'Return camera to home/default position.',
    input_schema: { type: 'object', properties: {} },
  },
  {
    name: 'recall_preset',
    description: 'Move camera to saved preset position (0–254).',
    input_schema: {
      type: 'object',
      properties: { preset_number: { type: 'integer', minimum: 0, maximum: 254 } },
      required: ['preset_number'],
    },
  },
  {
    name: 'save_preset',
    description: 'Save current camera position as a preset (0–254).',
    input_schema: {
      type: 'object',
      properties: { preset_number: { type: 'integer', minimum: 0, maximum: 254 } },
      required: ['preset_number'],
    },
  },
  {
    name: 'toggle_autotrack',
    description: "Enable or disable the camera's onboard auto-tracking. When enabled, camera follows subjects autonomously.",
    input_schema: {
      type: 'object',
      properties: { enabled: { type: 'boolean' } },
      required: ['enabled'],
    },
  },
  {
    name: 'set_white_balance',
    description: 'Set white balance mode.',
    input_schema: {
      type: 'object',
      properties: { mode: { type: 'string', enum: ['auto','indoor','outdoor','onepush','manual'] } },
      required: ['mode'],
    },
  },
  {
    name: 'set_exposure_mode',
    description: 'Set exposure/AE mode.',
    input_schema: {
      type: 'object',
      properties: { mode: { type: 'string', enum: ['auto','manual','shutter','iris','bright'] } },
      required: ['mode'],
    },
  },
  {
    name: 'switch_camera',
    description: 'Switch the active camera (1, 2, or 3). All subsequent commands target the new camera.',
    input_schema: {
      type: 'object',
      properties: { camera_id: { type: 'integer', enum: [1, 2, 3] } },
      required: ['camera_id'],
    },
  },
  {
    name: 'delay',
    description: 'Pause between simple sequential moves. For complex multi-direction patterns use execute_sequence instead.',
    input_schema: {
      type: 'object',
      properties: { ms: { type: 'integer', minimum: 100, maximum: 5000 } },
      required: ['ms'],
    },
  },
  {
    name: 'execute_sequence',
    description: 'Execute a pre-planned multi-step movement as a single smooth sequence — NO model round-trips between segments, NO stop between direction changes. Use for ANY multi-directional pattern: circles, scans, sweeps, figure-8s, zig-zags. Each segment immediately overrides the previous direction (motor transitions smoothly). Final stop is automatic. For a circle: plan 8 segments [right, rightdown, down, leftdown, left, leftup, up, rightup] at equal speed/duration.',
    input_schema: {
      type: 'object',
      properties: {
        segments: {
          type: 'array',
          description: 'Ordered movement segments — ALL planned at once before execution begins.',
          items: {
            type: 'object',
            properties: {
              direction:   { type: 'string', enum: ['left','right','up','down','leftup','rightup','leftdown','rightdown'] },
              pan_speed:   { type: 'integer', minimum: 1, maximum: 24, description: 'Consistent speed across segments gives smooth motion.' },
              tilt_speed:  { type: 'integer', minimum: 1, maximum: 20 },
              duration_ms: { type: 'integer', minimum: 100, maximum: 5000, description: 'Time to hold this direction before switching to next segment.' },
            },
            required: ['direction', 'pan_speed', 'tilt_speed', 'duration_ms'],
          },
          minItems: 2,
          maxItems: 64,
        },
      },
      required: ['segments'],
    },
  },
];
