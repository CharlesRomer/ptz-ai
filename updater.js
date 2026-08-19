// Auto-updater: polls GitHub every 30s, pulls changes, restarts server.
// Run this instead of server.js directly — it manages the server as a child process.
import { spawn, execSync } from 'child_process';

const POLL_MS = 30_000;
let server = null;

function log(msg) {
  const t = new Date().toLocaleTimeString();
  console.log(`[updater ${t}] ${msg}`);
}

function startServer() {
  log('Starting server...');
  server = spawn('node', ['server.js'], { stdio: 'inherit' });
  server.on('exit', code => {
    if (code !== null) log(`Server stopped (code ${code})`);
  });
}

function checkForUpdates() {
  try {
    execSync('git fetch origin', { stdio: 'pipe' });
    const local  = execSync('git rev-parse HEAD',  { stdio: 'pipe' }).toString().trim();
    const remote = execSync('git rev-parse @{u}',  { stdio: 'pipe' }).toString().trim();

    if (local === remote) return; // nothing new

    log('New version detected — pulling and restarting...');
    execSync('git pull', { stdio: 'inherit' });
    execSync('npm install --silent', { stdio: 'pipe' }); // in case dependencies changed

    if (server) { server.kill(); server = null; }
    setTimeout(startServer, 500); // brief pause before restart
  } catch (err) {
    log(`Update check failed: ${err.message}`);
  }
}

startServer();
setInterval(checkForUpdates, POLL_MS);
log(`Watching GitHub for updates every ${POLL_MS / 1000}s...`);
