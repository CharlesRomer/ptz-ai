// VISCA-over-IP (UDP) command module for PTZOptics G3 cameras
// Default port 1259 — set VISCA_PORT in .env to override
import { createSocket } from 'dgram';

const PORT = parseInt(process.env.VISCA_PORT) || 1259;
const cl = (v, lo, hi) => Math.max(lo, Math.min(hi, Math.round(v)));

// Pan/tilt direction byte pairs: [pan_dir, tilt_dir]
// pan: 01=left, 02=right, 03=stop  |  tilt: 01=up, 02=down, 03=stop
const PDIR = {
  left:      [0x01, 0x03],
  right:     [0x02, 0x03],
  up:        [0x03, 0x01],
  down:      [0x03, 0x02],
  leftup:    [0x01, 0x01],
  rightup:   [0x02, 0x01],
  leftdown:  [0x01, 0x02],
  rightdown: [0x02, 0x02],
};

// Fire-and-forget UDP send (low latency; we don't wait for ACK)
function send(ip, buf) {
  return new Promise((resolve, reject) => {
    const sock = createSocket('udp4');
    sock.send(buf, PORT, ip, (err) => {
      sock.close();
      if (err) return reject(err);
      resolve({ url: `visca://${ip}:${PORT}`, cmd: buf.toString('hex'), ok: true, status: 200 });
    });
  });
}

export const visca = {
  // Pan/tilt: 81 01 06 01 [pan_speed] [tilt_speed] [pan_dir] [tilt_dir] FF
  pan_tilt(ip, dir, ps, ts) {
    const [pd, td] = PDIR[dir] || [0x03, 0x03];
    return send(ip, Buffer.from([0x81, 0x01, 0x06, 0x01, cl(ps,1,24), cl(ts,1,20), pd, td, 0xFF]));
  },

  // Pan/tilt stop: 81 01 06 01 01 01 03 03 FF
  stop(ip) {
    return send(ip, Buffer.from([0x81, 0x01, 0x06, 0x01, 0x01, 0x01, 0x03, 0x03, 0xFF]));
  },

  // Zoom: tele=2p, wide=3p, stop=00 (p = speed 0-7)
  zoom(ip, dir, speed) {
    const s = cl(speed, 1, 7);
    const byte = dir === 'in' ? (0x20 | s) : dir === 'out' ? (0x30 | s) : 0x00;
    return send(ip, Buffer.from([0x81, 0x01, 0x04, 0x07, byte, 0xFF]));
  },

  zoom_stop(ip) {
    return send(ip, Buffer.from([0x81, 0x01, 0x04, 0x07, 0x00, 0xFF]));
  },

  // Focus: far=2p, near=3p, stop=00
  focus(ip, dir, speed) {
    const s = cl(speed, 1, 7);
    const byte = dir === 'far' ? (0x20 | s) : dir === 'near' ? (0x30 | s) : 0x00;
    return send(ip, Buffer.from([0x81, 0x01, 0x04, 0x08, byte, 0xFF]));
  },

  focus_stop(ip) {
    return send(ip, Buffer.from([0x81, 0x01, 0x04, 0x08, 0x00, 0xFF]));
  },

  // Auto focus: 81 01 04 38 02 FF | Manual: 81 01 04 38 03 FF
  focus_mode(ip, mode) {
    return send(ip, Buffer.from([0x81, 0x01, 0x04, 0x38, mode === 'auto' ? 0x02 : 0x03, 0xFF]));
  },

  // Home: 81 01 06 04 FF
  home(ip) {
    return send(ip, Buffer.from([0x81, 0x01, 0x06, 0x04, 0xFF]));
  },

  // Preset recall: 81 01 04 3F 02 [nn] FF
  preset_recall(ip, n) {
    return send(ip, Buffer.from([0x81, 0x01, 0x04, 0x3F, 0x02, cl(n,0,254), 0xFF]));
  },

  // Preset save: 81 01 04 3F 01 [nn] FF
  preset_save(ip, n) {
    return send(ip, Buffer.from([0x81, 0x01, 0x04, 0x3F, 0x01, cl(n,0,254), 0xFF]));
  },
};
