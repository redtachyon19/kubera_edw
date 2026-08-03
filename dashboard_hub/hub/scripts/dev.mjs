/**
 * Start both halves of the hub with one command and stop them together.
 *
 *   npm run dev            hub + every Streamlit dashboard
 *   npm run dev:web        hub only (dashboards already running elsewhere)
 *   npm run dev:dashboards dashboards only
 *
 * If either half dies, the other is torn down rather than left half-serving.
 */
import { spawn, spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

import { prefixLines, resolveDashboardsPython } from './dev-helpers.mjs';

const HUB_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..'); // dashboard_hub/hub
const ROOT_DIR = path.resolve(HUB_DIR, '..'); // dashboard_hub
const REPO_ROOT = path.resolve(ROOT_DIR, '..');
const RUN_LOCAL = path.join(ROOT_DIR, 'run_local.py');
const VITE_BIN = path.join(HUB_DIR, 'node_modules', 'vite', 'bin', 'vite.js');

const children = [];
let shuttingDown = false;

function pipeOutput(label, child) {
  for (const [stream, sink] of [
    [child.stdout, process.stdout],
    [child.stderr, process.stderr],
  ]) {
    if (!stream) continue;
    let carry = '';
    stream.setEncoding('utf8');
    stream.on('data', (chunk) => {
      const { output, carry: nextCarry } = prefixLines(label, carry, chunk);
      carry = nextCarry;
      if (output) sink.write(output);
    });
    stream.on('end', () => {
      if (carry) sink.write(`[${label}] ${carry}\n`);
      carry = '';
    });
  }
}

function killTree(child) {
  if (child.exitCode !== null || child.signalCode !== null || child.pid === undefined) return;
  if (process.platform === 'win32') {
    const result = spawnSync('taskkill', ['/pid', String(child.pid), '/T', '/F'], {
      stdio: 'ignore',
    });
    if (result.error) {
      console.error(`[dev] taskkill failed for pid ${child.pid}: ${result.error.message}`);
      child.kill('SIGKILL');
    }
    return;
  }
  child.kill('SIGTERM');
}

function shutdown(code) {
  if (shuttingDown) return;
  shuttingDown = true;
  for (const { child } of children) killTree(child);
  process.exitCode = code;
  setTimeout(() => process.exit(code), 300).unref();
}

function start(label, command, args, cwd) {
  const child = spawn(command, args, { cwd, stdio: ['ignore', 'pipe', 'pipe'], shell: false });
  children.push({ label, child });
  pipeOutput(label, child);

  child.on('error', (err) => {
    console.error(`[dev] failed to start ${label}: ${err.message}`);
    shutdown(1);
  });
  child.on('exit', (code, signal) => {
    if (shuttingDown) return;
    const how = signal ? `signal ${signal}` : `code ${code}`;
    console.error(`[dev] ${label} exited (${how}); stopping the other processes.`);
    shutdown(code ?? 1);
  });
}

function parseArgs(argv) {
  let web = true;
  let dashboards = true;
  for (const arg of argv) {
    if (arg === '--web-only') dashboards = false;
    else if (arg === '--dashboards-only') web = false;
    else throw new Error(`Unknown flag: ${arg} (expected --web-only or --dashboards-only)`);
  }
  return { web, dashboards };
}

function main() {
  let selection;
  try {
    selection = parseArgs(process.argv.slice(2));
  } catch (err) {
    console.error(`[dev] ${err.message}`);
    process.exit(2);
  }

  if (selection.dashboards) {
    if (!existsSync(RUN_LOCAL)) {
      console.error(`[dev] dashboard runner not found at ${RUN_LOCAL}`);
      process.exit(1);
    }
    let python;
    try {
      python = resolveDashboardsPython({
        repoRoot: REPO_ROOT,
        platform: process.platform,
        env: process.env,
        exists: existsSync,
        join: path.join,
      });
    } catch (err) {
      console.error(`[dev] ${err.message}`);
      process.exit(1);
    }
    start('dashboards', python, ['-u', RUN_LOCAL], ROOT_DIR);
  }

  if (selection.web) {
    if (!existsSync(VITE_BIN)) {
      console.error(`[dev] Vite is not installed at ${VITE_BIN}. Run \`npm install\` first.`);
      shutdown(1);
      return;
    }
    start('hub', process.execPath, [VITE_BIN], HUB_DIR);
  }

  for (const signal of ['SIGINT', 'SIGTERM']) {
    process.on(signal, () => {
      console.log(`\n[dev] ${signal} received — stopping the hub and the dashboards…`);
      shutdown(0);
    });
  }
}

main();
