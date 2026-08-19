// Persistent MJPEG stream manager — one long-lived ffmpeg process per camera IP.
// Keeps RTSP connection open continuously; parses raw JPEG frames from the byte stream
// and fans them out to HTTP MJPEG clients and Watch Mode frame consumers.
import { spawn } from 'child_process';

const IDLE_SHUTDOWN_MS = 60_000; // stop ffmpeg 60s after last client disconnects
const FRAME_TIMEOUT_MS = 8_000;  // give up waiting for first frame after 8s
const MAX_BUF_BYTES    = 4 * 1024 * 1024; // 4 MB safety cap on internal buffer
const FPS              = 15;     // sub-stream is already 640x360@30fps; 15 is smooth and halves encode work

class CameraStream {
  constructor(ip) {
    this.ip          = ip;
    this.proc        = null;
    this.buf         = Buffer.alloc(0);
    this.latestFrame = null;   // most recent raw JPEG Buffer
    this.listeners   = new Set(); // (frame: Buffer) => void
    this.idleTimer   = null;
    this.retryTimer  = null;
  }

  // ── Public API ─────────────────────────────────────────────────────────────

  /** Start stream if not already running (idempotent). */
  ensure() {
    if (this.proc || this.retryTimer) return;
    this._start();
  }

  /**
   * Subscribe to frames. Calls cb(Buffer) for every decoded JPEG.
   * Returns an unsubscribe function — call it when the client disconnects.
   */
  addListener(cb) {
    this.listeners.add(cb);
    if (this.idleTimer) { clearTimeout(this.idleTimer); this.idleTimer = null; }
    this.ensure();
    return () => this._removeListener(cb);
  }

  /** Resolve with the latest frame as base64, or wait up to 8s for the first one. */
  getFrameB64() {
    if (this.latestFrame) return Promise.resolve(this.latestFrame.toString('base64'));
    this.ensure();
    return new Promise((resolve, reject) => {
      const t = setTimeout(() => {
        this.listeners.delete(cb);
        reject(new Error(`No frame from ${this.ip} within ${FRAME_TIMEOUT_MS / 1000}s — camera offline?`));
      }, FRAME_TIMEOUT_MS);
      const cb = (frame) => {
        clearTimeout(t);
        this.listeners.delete(cb);
        resolve(frame.toString('base64'));
      };
      this.listeners.add(cb);
    });
  }

  /** Permanently stop the stream (called when idle timer fires). */
  stop() {
    if (this.retryTimer) { clearTimeout(this.retryTimer); this.retryTimer = null; }
    if (this.idleTimer)  { clearTimeout(this.idleTimer);  this.idleTimer  = null; }
    if (this.proc)       { this.proc.kill('SIGKILL');      this.proc = null; }
    this.latestFrame = null;
    this.buf         = Buffer.alloc(0);
  }

  // ── Internals ──────────────────────────────────────────────────────────────

  _start() {
    this.buf = Buffer.alloc(0);
    const proc = spawn('ffmpeg', [
      // Low-latency flags before -i so they apply to the input demuxer
      '-fflags',          'nobuffer',
      '-flags',           'low_delay',
      '-rtsp_transport',  'tcp',
      '-i',               `rtsp://${this.ip}:554/2`,  // sub-stream: 640x360@30fps — no scale needed, 18x fewer pixels than /1
      '-f',               'mjpeg',
      '-q:v',             '5',          // JPEG quality 1 (best) – 31 (worst)
      '-r',               String(FPS),  // 15fps output — sub-stream is 30fps; halves encode work
      '-loglevel',        'quiet',
      'pipe:1',
    ]);
    this.proc = proc;

    proc.stdout.on('data', (chunk) => {
      if (this.buf.length + chunk.length > MAX_BUF_BYTES) {
        // Safety: drop stale buffered data if we somehow fall behind
        this.buf = Buffer.alloc(0);
      }
      this.buf = Buffer.concat([this.buf, chunk]);
      this._parseFrames();
    });

    proc.on('close', () => {
      this.proc = null;
      if (this.listeners.size > 0) {
        // Reconnect after a short delay
        this.retryTimer = setTimeout(() => {
          this.retryTimer = null;
          this._start();
        }, 2000);
      }
    });

    proc.on('error', () => { this.proc = null; });
  }

  _parseFrames() {
    // JPEG SOI = FF D8, EOI = FF D9.
    // Within JPEG scan data, FF bytes are byte-stuffed as FF 00, so FF D9
    // can only ever appear as the genuine EOI marker — the search is unambiguous.
    while (this.buf.length >= 4) {
      // Find SOI
      const soi = this.buf.indexOf(0xFF);
      if (soi === -1 || soi >= this.buf.length - 1) { this.buf = Buffer.alloc(0); return; }
      if (this.buf[soi + 1] !== 0xD8) {
        // Not FF D8 — skip one byte and retry
        this.buf = this.buf.slice(soi + 1);
        continue;
      }

      // Discard garbage before SOI
      if (soi > 0) this.buf = this.buf.slice(soi);

      // Find EOI starting from byte 2 (after FF D8)
      let eoi = -1;
      for (let i = 2; i < this.buf.length - 1; i++) {
        if (this.buf[i] === 0xFF && this.buf[i + 1] === 0xD9) { eoi = i; break; }
      }
      if (eoi === -1) return; // incomplete frame — wait for more data

      const frame      = Buffer.from(this.buf.slice(0, eoi + 2));
      this.buf         = this.buf.slice(eoi + 2);
      this.latestFrame = frame;

      for (const cb of this.listeners) {
        try { cb(frame); } catch (_) {}
      }
    }
  }

  _removeListener(cb) {
    this.listeners.delete(cb);
    if (this.listeners.size === 0) {
      this.idleTimer = setTimeout(() => {
        if (this.listeners.size === 0) this.stop();
      }, IDLE_SHUTDOWN_MS);
    }
  }
}

// ── Registry ──────────────────────────────────────────────────────────────────
const registry = new Map(); // ip → CameraStream

export function getStream(ip) {
  if (!registry.has(ip)) registry.set(ip, new CameraStream(ip));
  return registry.get(ip);
}

export function stopAllStreams() {
  for (const s of registry.values()) s.stop();
  registry.clear();
}
