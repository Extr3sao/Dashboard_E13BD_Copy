import { spawn } from 'node:child_process';
import net from 'node:net';
import process from 'node:process';
import { chromium } from 'playwright';

export async function launchBrowser(logStep) {
  try {
    if (logStep) await logStep('launch msedge');
    return await chromium.launch({ channel: 'msedge', headless: true });
  } catch {
    if (logStep) await logStep('fallback chromium');
    return chromium.launch({ headless: true });
  }
}

export async function waitForServerOrExit(url, child, timeoutMs = 45000) {
  const deadline = Date.now() + timeoutMs;
  let lastError = null;
  while (Date.now() < deadline) {
    if (child && child.exitCode !== null) {
      throw new Error(`el procés ha acabat abans d'estar llest (exitCode=${child.exitCode})`);
    }
    try {
      const response = await fetch(url);
      if (response.ok) return;
    } catch (error) {
      lastError = error;
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`servidor no disponible a temps (${url}): ${lastError?.message || 'timeout'}`);
}

export function startProcess(
  command,
  args,
  options,
  shutdownState,
  unexpectedExitLabel = command,
  handlers = {},
) {
  const child = spawn(command, args, options);
  const handleStdout = typeof handlers.onStdout === 'function'
    ? handlers.onStdout
    : (chunk) => {
        if (!shutdownState.requested) {
          process.stdout.write(chunk);
        }
      };
  const handleStderr = typeof handlers.onStderr === 'function'
    ? handlers.onStderr
    : (chunk) => {
        if (!shutdownState.requested) {
          process.stderr.write(chunk);
        }
      };
  child.stdout.on('data', (chunk) => {
    handleStdout(chunk);
  });
  child.stderr.on('data', (chunk) => {
    handleStderr(chunk);
  });
  child.on('exit', (code) => {
    if (!shutdownState.requested && code !== 0 && code !== null) {
      process.stderr.write(`${unexpectedExitLabel} ha finalitzat amb codi ${code}\n`);
    }
  });
  return child;
}

export async function closeProcess(child, shutdownState, logStep) {
  if (!child || child.killed || !child.pid) return;
  shutdownState.requested = true;

  if (process.platform === 'win32') {
    if (logStep) {
      await logStep(`taskkill process tree ${child.pid}`);
    }
    await new Promise((resolve) => {
      const killer = spawn('taskkill', ['/pid', String(child.pid), '/T', '/F'], {
        windowsHide: true,
        stdio: 'ignore',
      });
      killer.once('exit', () => resolve());
      killer.once('error', () => resolve());
    });
    return;
  }

  child.kill('SIGTERM');
  await new Promise((resolve) => {
    const timeout = setTimeout(resolve, 4000);
    child.once('exit', () => {
      clearTimeout(timeout);
      resolve();
    });
  });
}

function isPortFree(host, port) {
  return new Promise((resolve) => {
    const socket = net.createConnection({ host, port });

    const finish = (value) => {
      socket.removeAllListeners();
      socket.destroy();
      resolve(value);
    };

    socket.once('connect', () => finish(false));
    socket.once('error', (error) => {
      if (error && ['ECONNREFUSED', 'EHOSTUNREACH', 'ETIMEDOUT'].includes(error.code)) {
        finish(true);
        return;
      }
      finish(false);
    });
  });
}

export async function waitForPortToBeFree(host, port, timeoutMs = 10000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await isPortFree(host, port)) return;
    await new Promise((resolve) => setTimeout(resolve, 300));
  }
  throw new Error(`el port ${host}:${port} continua ocupat després del tancament`);
}

export async function startServiceWithRetries({
  label,
  startFn,
  readyUrl,
  closeFn,
  logStep,
  timeoutMs = 45000,
  maxAttempts = 3,
}) {
  let child = null;
  let lastError = null;
  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    if (logStep) await logStep(`${label} start attempt ${attempt}/${maxAttempts}`);
    child = startFn();
    try {
      await waitForServerOrExit(readyUrl, child, timeoutMs);
      if (logStep) await logStep(`${label} ready on attempt ${attempt}`);
      return child;
    } catch (error) {
      lastError = error;
      if (logStep) await logStep(`${label} start attempt ${attempt} failed: ${error.message}`);
      await closeFn(child);
      child = null;
      if (attempt < maxAttempts) {
        await new Promise((resolve) => setTimeout(resolve, 1500 * attempt));
      }
    }
  }
  throw new Error(`${label} no ha arrencat després de ${maxAttempts} intents: ${lastError?.message || 'error desconegut'}`);
}



