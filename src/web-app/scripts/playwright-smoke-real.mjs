import { appendFile, mkdir, rm, writeFile } from 'node:fs/promises';
import { spawn } from 'node:child_process';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';
import { closeProcess as runtimeCloseProcess, launchBrowser, startProcess as runtimeStartProcess, startServiceWithRetries as runtimeStartServiceWithRetries, waitForPortToBeFree } from './smokeRuntime.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const webAppRoot = path.resolve(__dirname, '..');
const repoRoot = path.resolve(webAppRoot, '..', '..');
const outputDir = path.join(webAppRoot, 'output', 'playwright', 'real-backend');
const envDir = path.join(outputDir, 'env');
const debugLogPath = path.join(outputDir, 'real-backend-smoke.log');
const backendPort = 8012;
const baseUrl = `http://127.0.0.1:${backendPort}`;

const shutdownState = { requested: false };

async function appendDebug(message) {
  await appendFile(debugLogPath, `${message}\n`, 'utf8');
}

function appendDebugChunk(prefix, chunk) {
  const text = String(chunk || '');
  appendFile(debugLogPath, `${prefix}${text}`, 'utf8').catch(() => {});
}

async function logStep(message) {
  const line = `[smoke-real] ${message}`;
  console.log(line);
  await appendDebug(line);
}

function startBackendServer(env) {
  if (process.platform === 'win32') {
    return runtimeStartProcess(
      'cmd.exe',
      ['/d', '/s', '/c', `.\\.venv\\Scripts\\python.exe -m uvicorn src.api.main:app --host 127.0.0.1 --port ${backendPort}`],
      {
        cwd: repoRoot,
        stdio: ['ignore', 'pipe', 'pipe'],
        windowsHide: true,
        env,
      },
      shutdownState,
      'Proces backend real',
      {
        onStdout: (chunk) => appendDebugChunk('[backend stdout] ', chunk),
        onStderr: (chunk) => appendDebugChunk('[backend stderr] ', chunk),
      },
    );
  }

  return runtimeStartProcess(
    '.venv/Scripts/python.exe',
    ['-m', 'uvicorn', 'src.api.main:app', '--host', '127.0.0.1', '--port', String(backendPort)],
    {
      cwd: repoRoot,
      stdio: ['ignore', 'pipe', 'pipe'],
      env,
    },
    shutdownState,
    'Proces backend real',
    {
      onStdout: (chunk) => appendDebugChunk('[backend stdout] ', chunk),
      onStderr: (chunk) => appendDebugChunk('[backend stderr] ', chunk),
    },
  );
}

async function closeProcess(child) {
  await runtimeCloseProcess(child, shutdownState);
}

async function startServiceWithRetries(label, startFn, env, readyUrl, timeoutMs = 45000, maxAttempts = 3) {
  return runtimeStartServiceWithRetries({
    label,
    startFn: () => startFn(env),
    readyUrl,
    closeFn: (child) => closeProcess(child),
    logStep,
    timeoutMs,
    maxAttempts,
  });
}

async function runSeedScriptOnce(env) {
  await new Promise((resolve, reject) => {
    const child = spawn(
      process.platform === 'win32' ? 'cmd.exe' : '.venv/Scripts/python.exe',
      process.platform === 'win32'
        ? ['/d', '/s', '/c', '.\\.venv\\Scripts\\python.exe scripts\\seed_real_backend_smoke.py']
        : ['scripts/seed_real_backend_smoke.py'],
      {
        cwd: repoRoot,
        stdio: ['ignore', 'pipe', 'pipe'],
        windowsHide: true,
        env,
      },
    );
    child.stdout.on('data', (chunk) => process.stdout.write(chunk));
    child.stderr.on('data', (chunk) => process.stderr.write(chunk));
    child.once('exit', (code) => {
      if (code === 0) resolve();
      else reject(new Error(`Seed script ha finalitzat amb codi ${code}`));
    });
    child.once('error', reject);
  });
}

async function runSeedScriptWithRetries(env, maxAttempts = 3) {
  let lastError = null;
  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    await logStep(`seed backend data attempt ${attempt}/${maxAttempts}`);
    try {
      await runSeedScriptOnce(env);
      await logStep(`seed backend data ready on attempt ${attempt}`);
      return;
    } catch (error) {
      lastError = error;
      await logStep(`seed backend data attempt ${attempt} failed: ${error.message}`);
      if (attempt < maxAttempts) {
        await new Promise((resolve) => setTimeout(resolve, 1500 * attempt));
      }
    }
  }
  throw new Error(`seed backend data no ha completat després de ${maxAttempts} intents: ${lastError?.message || 'error desconegut'}`);
}

async function verifyText(page, text) {
  await page.waitForFunction((value) => {
    const isVisible = (element) => {
      if (!element) return false;
      const style = window.getComputedStyle(element);
      if (style.visibility === 'hidden' || style.display === 'none') return false;
      return Boolean(element.offsetWidth || element.offsetHeight || element.getClientRects().length);
    };
    return Array.from(document.querySelectorAll('body *')).some((element) => (
      isVisible(element) && element.textContent?.includes(value)
    ));
  }, text, { timeout: 15000 });
}

async function expectDownload(page, trigger, expectedFileName) {
  const [download] = await Promise.all([
    page.waitForEvent('download', { timeout: 15000 }),
    trigger(),
  ]);
  const suggestedName = String(download.suggestedFilename() || '').trim();
  if (suggestedName !== expectedFileName) {
    throw new Error(`Nom de fitxer inesperat. Esperat: ${expectedFileName}. Rebut: ${suggestedName}`);
  }
  const downloadPath = await download.path();
  if (!downloadPath) {
    throw new Error(`No s'ha resolt cap path de descÃ rrega per a ${expectedFileName}`);
  }
}

async function expectClientSideDownload(page, trigger, expectedFileName) {
  await trigger();
  await page.waitForFunction((value) => {
    const events = Array.isArray(window.__downloadEvents) ? window.__downloadEvents : [];
    return events.some((item) => String(item?.download || '').trim() === value);
  }, expectedFileName, { timeout: 15000 });
}

async function expectAttachmentResponse(page, trigger, urlPart, expectedFileName) {
  const [response] = await Promise.all([
    page.waitForResponse((candidate) => candidate.url().includes(urlPart) && candidate.ok(), { timeout: 15000 }),
    trigger(),
  ]);
  const disposition = String(response.headers()['content-disposition'] || '').trim();
  if (!disposition.includes(expectedFileName)) {
    throw new Error('Content-Disposition inesperat per a ' + expectedFileName + ': ' + disposition);
  }
}

async function clickSubtab(page, name) {
  await page.getByRole('button', { name }).click();
}

async function runRealSmoke(page) {
  await logStep('goto app');
  await page.goto(baseUrl, { waitUntil: 'domcontentloaded' });

  await logStep('verify shell');
  await verifyText(page, 'Oracle Audit');
  await verifyText(page, 'E13DB');

  await logStep('post-crq checks load');
  await clickSubtab(page, 'Auditoria de canvis');
  await verifyText(page, 'Control de qualitat post-CRQ');
  await verifyText(page, 'CHECK_01');

  await logStep('automation dashboard and monthly pdf');
  await clickSubtab(page, 'Automatitzacions');
  await verifyText(page, "auditories");
  await page.getByRole('button', { name: /^Dashboard/i }).click();
  await verifyText(page, 'Execucions');
  const analyticsMonth = await page.locator('input[type="month"]').inputValue();
  await expectDownload(
    page,
    () => page.getByRole('button', { name: /^PDF mensual$/i }).click(),
    `dashboard_automatitzacions_${analyticsMonth}.pdf`,
  );

  await logStep('automation jobs with real backend');
  await page.getByRole('button', { name: /^Jobs/i }).click();
  await verifyText(page, 'Job real backend');
  const jobForm = page.locator('#job_form');
  await jobForm.locator('input').first().fill('Job creat backend real');
  await jobForm.getByRole('button', { name: /Crea job/i }).click();
  await verifyText(page, 'Job creat backend real');

  await logStep('automation history and retry queue');
  await page.getByRole('button', { name: /^Històric/i }).click();
  await verifyText(page, "Històric d'execucions");
  await verifyText(page, 'Job real backend');
  const historyPanel = page.locator('#history');
  const firstRunRow = historyPanel.locator('tbody tr').first();
  await historyPanel.getByRole('button', { name: /^Lots$/i }).first().click();
  await verifyText(page, 'LOT_AUX');
  await expectAttachmentResponse(
    page,
    () => firstRunRow.getByRole('link', { name: /^Informe$/i }).click(),
    '/api/automation/runs/1/report',
    'real_backend_run_report.pdf',
  );
  await expectClientSideDownload(
    page,
    () => firstRunRow.getByRole('button', { name: /^CSV$/i }).click(),
    'automation_run_1_lots.csv',
  );
  await page.getByRole('button', { name: /^Reintents/i }).click();
  await verifyText(page, 'Cua de reintents');
  await verifyText(page, 'LOT_APP');

  await logStep('automation recipients and templates');
  await page.getByRole('button', { name: /^Destinataris/i }).click();
  await verifyText(page, 'app@example.com');
  const recipientsPanel = page.locator('#lot_routes');
  const routeLabelInput = recipientsPanel.getByPlaceholder('Etiqueta visible').first();
  await routeLabelInput.fill('Aplicacions Reals');
  await recipientsPanel.getByRole('button', { name: /Desa rutes/i }).click();
  await verifyText(page, 'Destinataris per lot desats.');
  if ((await routeLabelInput.inputValue()) !== 'Aplicacions Reals') {
    throw new Error("No s'ha persistit l'etiqueta de destinataris esperada");
  }
  await page.getByRole('button', { name: /^Plantilles/i }).click();
  const templatesPanel = page.locator('#templates');
  const firstSubjectInput = templatesPanel.getByPlaceholder('Assumpte').first();
  await firstSubjectInput.fill('Assumpte real updated');
  await templatesPanel.getByRole('button', { name: /Desa plantilles/i }).click();
  await verifyText(page, 'Plantilles desades.');
  if ((await firstSubjectInput.inputValue()) !== 'Assumpte real updated') {
    throw new Error("No s'ha persistit l'assumpte de plantilla esperat");
  }

  await logStep('rules and tasks');
  await clickSubtab(page, 'Tasques i regles');
  await verifyText(page, 'Revisar LOT_APP');
  await verifyText(page, 'ALT');
  await page.getByRole('button', { name: /Resoldre/i }).first().click();
  await verifyText(page, 'Tasca actualitzada.');
  await page.getByRole('button', { name: /Crear regla/i }).click();
  await verifyText(page, 'Regla global creada.');

  await logStep('mail config save');
  await clickSubtab(page, /Configuraci.*servidor/i);
  await verifyText(page, 'Servidor de Correu (SMTP)');
  await page.getByPlaceholder('Ex: smtp.office365.com').fill('smtp.real.updated');
  await page.getByRole('button', { name: /Desar Configuraci/i }).click();
  await verifyText(page, 'desada correctament');

  await logStep('obsolets registry real backend');
  await clickSubtab(page, "Repositori d'obsolets");
  await verifyText(page, 'TMP_REAL');
  const registryInputs = page.locator('input');
  await registryInputs.nth(0).fill('APP_UI');
  await registryInputs.nth(1).fill('TMP_UI_REAL');
  await page.locator('textarea').fill('Alta des de smoke real');
  await page.getByRole('button', { name: /Afegir al registre/i }).click();
  await verifyText(page, 'TMP_UI_REAL');

  await logStep('tutorial');
  await clickSubtab(page, 'Guia i Ajuda');
  await verifyText(page, 'Tutorial');
  await verifyText(page, 'Arquitectura');
}

async function prepareEnvironment() {
  await mkdir(outputDir, { recursive: true });
  await mkdir(envDir, { recursive: true });
  await writeFile(debugLogPath, '', 'utf8');

  const connectionsFile = path.join(envDir, 'Cadena_conexions.txt');
  const internalDbPath = path.join(envDir, 'internal.real-smoke.db');
  const automationDbPath = path.join(envDir, 'automation.real-smoke.db');

  await rm(internalDbPath, { force: true });
  await rm(automationDbPath, { force: true });

  await writeFile(
    connectionsFile,
    [
      '## E13DB',
      'USER = demo',
      'PASSWORD = demo',
      'DSN = 127.0.0.1:1521/ORCLCDB',
      '',
    ].join('\n'),
    'utf8',
  );

  return {
    CONNECTIONS_FILE: connectionsFile,
    DEFAULT_PROFILE: 'E13DB',
    INTERNAL_DB_PATH: internalDbPath,
    AUTOMATION_DB_PATH: automationDbPath,
    REAL_SMOKE_OUTPUT_DIR: outputDir,
  };
}

async function main() {
  let browser;
  let backendServer;
  try {
    const envOverrides = await prepareEnvironment();
    const backendEnv = { ...process.env, ...envOverrides };

    await runSeedScriptWithRetries(backendEnv);
    backendServer = await startServiceWithRetries(
      'real-backend',
      startBackendServer,
      backendEnv,
      `http://127.0.0.1:${backendPort}/api/profiles`,
      45000,
      3,
    );

    browser = await launchBrowser(logStep);
    const context = await browser.newContext({ acceptDownloads: true });
    const page = await context.newPage();
    await page.addInitScript(() => {
      window.__downloadEvents = [];
      const originalClick = HTMLAnchorElement.prototype.click;
      HTMLAnchorElement.prototype.click = function patchedAnchorClick(...args) {
        try {
          if (this.download) {
            window.__downloadEvents.push({ download: this.download, href: this.href });
          }
        } catch {
          // Ignore tracking failures.
        }
        return originalClick.apply(this, args);
      };
    });
    await runRealSmoke(page);
    await context.close();
    await logStep('real backend smoke completed');
  } finally {
    if (browser) await browser.close();
    await closeProcess(backendServer);
    await logStep('verify backend port released');
    await waitForPortToBeFree('127.0.0.1', backendPort, 15000);
  }
}

main().catch(async (error) => {
  console.error(error);
  try {
    await appendDebug(String(error?.stack || error));
  } finally {
    process.exitCode = 1;
  }
});
