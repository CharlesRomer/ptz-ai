import { Atem } from 'atem-connection';

const ATEM_IP = process.env.ATEM_IP;

// ATEM input numbers for each PTZ camera (default 1, 2, 3)
export const CAM_ATEM_INPUTS = {
  1: parseInt(process.env.ATEM_CAM1_INPUT || '1'),
  2: parseInt(process.env.ATEM_CAM2_INPUT || '2'),
  3: parseInt(process.env.ATEM_CAM3_INPUT || '3'),
};

let atem = null;
let connected = false;

export function getATEMStatus() {
  if (!ATEM_IP) return { configured: false };
  if (!connected || !atem?.state) return { configured: true, connected: false };

  const me = atem.state.video?.mixEffects?.[0];
  if (!me) return { configured: true, connected: true, error: 'No ME state' };

  const pgm = me.programInput;
  const pvw = me.previewInput;
  const inputs = atem.state.inputs || {};

  const getName = (id) => inputs[id]?.longName || inputs[id]?.shortName || `Input ${id}`;

  // Build tally map: cameraid → { program, preview }
  const tally = {};
  for (const [camId, atInput] of Object.entries(CAM_ATEM_INPUTS)) {
    tally[camId] = { program: pgm === atInput, preview: pvw === atInput };
  }

  return {
    configured: true,
    connected: true,
    programInput: pgm,
    previewInput: pvw,
    programName: getName(pgm),
    previewName: getName(pvw),
    tally,
  };
}

export function initATEM() {
  if (!ATEM_IP) {
    console.log('[ATEM] Not configured — add ATEM_IP to .env to enable');
    return;
  }

  atem = new Atem();

  atem.on('connected', () => {
    connected = true;
    console.log(`[ATEM] Connected to ${ATEM_IP}`);
  });

  atem.on('disconnected', () => {
    connected = false;
    console.log('[ATEM] Disconnected — library will auto-retry');
  });

  atem.on('error', (err) => {
    console.error('[ATEM] Error:', err);
  });

  atem.connect(ATEM_IP);
  console.log(`[ATEM] Connecting to ${ATEM_IP}…`);
}
