import { OBSWebSocket } from 'obs-websocket-js';

const OBS_URL  = process.env.OBS_WS_URL;
const OBS_PASS = process.env.OBS_WS_PASSWORD || '';

let obs = null;
let connected = false;
let cached = { configured: false };
let refreshTimer = null;

export function getOBSStatus() {
  return cached;
}

async function refresh() {
  if (!obs || !connected) return;
  try {
    const [stream, record, scene, stats] = await Promise.all([
      obs.call('GetStreamStatus'),
      obs.call('GetRecordStatus'),
      obs.call('GetCurrentProgramScene'),
      obs.call('GetStats'),
    ]);

    let bitrateKbps = null;
    if (stream.outputActive && stream.outputBytes > 0 && stream.outputDuration > 0) {
      bitrateKbps = Math.round((stream.outputBytes * 8) / stream.outputDuration);
    }

    cached = {
      configured: true,
      connected: true,
      streaming: stream.outputActive,
      recording: record.outputActive,
      scene: scene.currentProgramSceneName,
      bitrateKbps,
      fps: Math.round(stats.activeFps ?? 0),
      cpuUsage: Math.round(stats.cpuUsage ?? 0),
      droppedFrames: stats.renderSkippedFrames ?? 0,
    };
  } catch (err) {
    cached = { configured: true, connected: true, refreshError: err.message };
  }
}

async function connect() {
  try {
    await obs.connect(OBS_URL, OBS_PASS || undefined);
    connected = true;
    cached = { configured: true, connected: true };
    console.log(`[OBS]  Connected to ${OBS_URL}`);
    await refresh();
  } catch (err) {
    connected = false;
    cached = { configured: true, connected: false, error: err.message };
    console.log(`[OBS]  Connection failed: ${err.message} — retry in 15s`);
    setTimeout(connect, 15_000);
  }
}

export async function initOBS() {
  if (!OBS_URL) {
    console.log('[OBS]  Not configured — add OBS_WS_URL to .env to enable');
    return;
  }

  obs = new OBSWebSocket();

  obs.on('ConnectionClosed', () => {
    connected = false;
    cached = { configured: true, connected: false };
    console.log('[OBS]  Disconnected — retry in 15s');
    setTimeout(connect, 15_000);
  });

  await connect();

  refreshTimer = setInterval(refresh, 4_000);
}
