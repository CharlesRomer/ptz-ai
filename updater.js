// Auto-updater: polls GitHub every 30s, pulls changes, restarts server.
// Also auto-restarts the server if it crashes for any reason.
import { spawn, execSync } from 'child_process';

const POLL_MS    = 30_000;
const RESTART_MS = 3_000; // wait before restarting after a crash
let server       = null;
let updating     = false; // prevent restart race during a git pull

function log(msg) {
  const t = new Date().toLocaleTimeString();
  console.log(`[updater ${t}] ${msg}`);
}

function startServer() {
  if (updating) return;
  log('Starting server...');
  server = spawn('node', ['server.js'], { stdio: 'inherit' });

  server.on('exit', (code, signal) => {
    server = null;
    if (updating) return; // deliberate kill for update — don't restart here
    if (signal === 'SIGKILL' || signal === 'SIGTERM') return;
    log(`Server exited (code ${code}) — restarting in ${RESTART_MS / 1000}s...`);
    setTimeout(startServer, RESTART_MS);
  });
}

function checkForUpdates() {
  try {
    execSync('git fetch origin', { stdio: 'pipe' });
    const local  = execSync('git rev-parse HEAD', { stdio: 'pipe' }).toString().trim();
    const remote = execSync('git rev-parse @{u}', { stdio: 'pipe' }).toString().trim();
    if (local === remote) return;

    log('New version detected — pulling and restarting...');
    updating = true;
    if (server) { server.kill(); server = null; }

    execSync('git pull', { stdio: 'inherit' });
    execSync('npm install --silent', { stdio: 'pipe' });

    updating = false;
    setTimeout(startServer, 500);
  } catch (err) {
    updating = false;
    log(`Update check failed: ${err.message}`);
  }
}

startServer();
setInterval(checkForUpdates, POLL_MS);
log(`Watching GitHub for updates every ${POLL_MS / 1000}s...`);
