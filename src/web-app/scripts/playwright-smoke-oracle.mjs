import { access, appendFile, copyFile, mkdir, rm, writeFile } from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';
import { closeProcess as runtimeCloseProcess, launchBrowser, startProcess as runtimeStartProcess, startServiceWithRetries as runtimeStartServiceWithRetries } from './smokeRuntime.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const webAppRoot = path.resolve(__dirname, '..');
const repoRoot = path.resolve(webAppRoot, '..', '..');
const outputDir = path.join(webAppRoot, 'output', 'playwright', 'oracle-backend');
const envDir = path.join(outputDir, 'env');
const debugLogPath = path.join(outputDir, 'oracle-backend-smoke.log');
const backendPort = 8013;
const vitePort = 4177;
const baseUrl = `http://127.0.0.1:${vitePort}`;
const defaultInternalDbSource = path.join(repoRoot, 'src', 'db', 'internal.db');
const postCrqRunTimeoutMs = 300000;
const postCrqReportTimeoutMs = 300000;

const shutdownState = { requested: false };

async function appendDebug(message) {
  await mkdir(path.dirname(debugLogPath), { recursive: true });
  await appendFile(debugLogPath, `${message}\n`, 'utf8');
}

function appendDebugChunk(prefix, chunk) {
  const text = String(chunk || '');
  appendFile(debugLogPath, `${prefix}${text}`, 'utf8').catch(() => {});
}

async function logStep(message) {
  const line = `[smoke-oracle] ${message}`;
  console.log(line);
  await appendDebug(line);
}

function requireEnv(name) {
  const value = String(process.env[name] || '').trim();
  if (!value) {
    throw new Error(`Falta la variable requerida ${name}`);
  }
  return value;
}

async function ensureReadable(filePath, label) {
  try {
    await access(filePath);
  } catch {
    throw new Error(`${label} no existe o no es accesible: ${filePath}`);
  }
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
      'Proces backend Oracle',
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
    'Proces backend Oracle',
    {
      onStdout: (chunk) => appendDebugChunk('[backend stdout] ', chunk),
      onStderr: (chunk) => appendDebugChunk('[backend stderr] ', chunk),
    },
  );
}

function startViteServer(env) {
  if (process.platform === 'win32') {
    return runtimeStartProcess(
      'cmd.exe',
      ['/d', '/s', '/c', `npm run dev -- --host 127.0.0.1 --port ${vitePort} --strictPort`],
      {
        cwd: webAppRoot,
        stdio: ['ignore', 'pipe', 'pipe'],
        windowsHide: true,
        env,
      },
      shutdownState,
      'Proces Vite Oracle',
    );
  }

  return runtimeStartProcess(
    'npm',
    ['run', 'dev', '--', '--host', '127.0.0.1', '--port', String(vitePort), '--strictPort'],
    {
      cwd: webAppRoot,
      stdio: ['ignore', 'pipe', 'pipe'],
      env,
    },
    shutdownState,
    'Proces Vite Oracle',
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

async function verifyText(page, text, timeout = 15000) {
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
  }, text, { timeout });
}

async function waitForSelectedChecks(page, timeout = 30000) {
  await page.waitForFunction(() => {
    const match = document.body.innerText.match(/Seleccionats:\s*(\d+)/i);
    return match && Number(match[1]) > 0;
  }, { timeout });
}

async function expectAttachmentResponse(page, trigger, urlPart, fileNamePattern, timeout = postCrqReportTimeoutMs) {
  const [response] = await Promise.all([
    page.waitForResponse((candidate) => candidate.url().includes(urlPart) && candidate.ok(), { timeout }),
    trigger(),
  ]);
  const disposition = String(response.headers()['content-disposition'] || '').trim();
  if (!fileNamePattern.test(disposition)) {
    throw new Error(`Content-Disposition inesperat: ${disposition}`);
  }
}

async function clickSubtab(page, name) {
  await page.getByRole('button', { name }).click();
}

async function waitForEnabledButtonText(page, buttonText, timeout = 30000) {
  await page.waitForFunction((expectedText) => {
    const candidates = Array.from(document.querySelectorAll('button'));
    return candidates.some((candidate) => (
      candidate.textContent?.trim() === expectedText
      && !candidate.disabled
    ));
  }, buttonText, { timeout });
}

async function listProviderOptions(page) {
  const providerSelect = page.locator('select').nth(2);
  if (await providerSelect.count() === 0) {
    return [];
  }
  return providerSelect.locator('option').evaluateAll((options) => options.map((option) => ({
    value: String(option.value || '').trim(),
    label: String(option.textContent || '').trim(),
  })));
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  return { response, data };
}

async function prepareEnvironment() {
  const rawConnectionsFile = requireEnv('ORACLE_SMOKE_CONNECTIONS_FILE');
  const connectionsFile = path.isAbsolute(rawConnectionsFile)
    ? rawConnectionsFile
    : path.resolve(repoRoot, rawConnectionsFile);
  const profile = requireEnv('ORACLE_SMOKE_PROFILE');
  const schema = requireEnv('ORACLE_SMOKE_SCHEMA').toUpperCase();
  const postCrqSchemas = String(process.env.ORACLE_SMOKE_POST_CRQ_SCHEMAS || schema).trim().toUpperCase();
  const requireProvider = ['1', 'true', 'yes'].includes(String(process.env.ORACLE_SMOKE_REQUIRE_PROVIDER || '').trim().toLowerCase());
  const rawInternalDbSource = String(process.env.ORACLE_SMOKE_INTERNAL_DB_SOURCE || '').trim();
  const internalDbSource = rawInternalDbSource
    ? (path.isAbsolute(rawInternalDbSource) ? rawInternalDbSource : path.resolve(repoRoot, rawInternalDbSource))
    : defaultInternalDbSource;

  await ensureReadable(connectionsFile, 'El fitxer de connexions Oracle');
  await ensureReadable(internalDbSource, 'La base interna de cataleg');

  await mkdir(outputDir, { recursive: true });
  await mkdir(envDir, { recursive: true });
  await writeFile(debugLogPath, '', 'utf8');

  const internalDbPath = path.join(envDir, 'internal.oracle-smoke.db');
  const automationDbPath = path.join(envDir, 'automation.oracle-smoke.db');
  await rm(internalDbPath, { force: true });
  await rm(automationDbPath, { force: true });
  await copyFile(internalDbSource, internalDbPath);

  return {
    profile,
    schema,
    postCrqSchemas,
    requireProvider,
    internalDbSource,
    backendEnv: {
      ...process.env,
      CONNECTIONS_FILE: connectionsFile,
      DEFAULT_PROFILE: profile,
      INTERNAL_DB_PATH: internalDbPath,
      AUTOMATION_DB_PATH: automationDbPath,
    },
    viteEnv: {
      ...process.env,
      VITE_API_PROXY_TARGET: `http://127.0.0.1:${backendPort}`,
      BROWSER: 'none',
    },
  };
}

async function verifyOracleProfile(profile) {
  await logStep(`oracle precheck profile ${profile}`);
  const { data } = await postJson(`http://127.0.0.1:${backendPort}/api/db/test`, { profile });
  if (data?.status !== 'success') {
    throw new Error(`Precheck Oracle fallit per al perfil ${profile}: ${data?.message || 'resposta desconeguda'}`);
  }
}

async function runOracleSmoke(page, profile, schema, postCrqSchemas, requireProvider) {
  await logStep('goto app');
  await page.goto(baseUrl, { waitUntil: 'domcontentloaded' });

  await logStep('verify shell');
  await verifyText(page, 'Oracle Audit');
  await verifyText(page, profile);

  await logStep('deep scan with oracle');
  await clickSubtab(page, /^An.*obsolets/i);
  await page.getByPlaceholder('Ex: MGR_APP, USER_DB...').fill(schema);
  await page.getByRole('button', { name: /^Auditar$/i }).click();
  await verifyText(page, `Detalls: ${schema}`, 120000);

  await logStep('post-crq with oracle');
  await clickSubtab(page, /Auditoria de canvis/i);
  await verifyText(page, 'Control de qualitat post-CRQ');
  await verifyText(page, 'CHECK_01', 30000);
  await page.getByPlaceholder('APP_USER, CORE_DB').fill(postCrqSchemas);
  await page.getByRole('button', { name: /^Tots$/i }).click();
  await waitForSelectedChecks(page, 30000);
  const executeButton = page.getByRole('button', { name: /^Executar$/i });
  await executeButton.waitFor({ state: 'visible', timeout: 30000 });
  await page.waitForFunction(() => {
    const button = Array.from(document.querySelectorAll('button')).find((candidate) => (
      candidate.textContent?.trim() === 'Executar'
    ));
    return button && !button.disabled;
  }, { timeout: 30000 });
  await Promise.all([
    page.waitForResponse((response) => (
      response.url().includes('/api/audit/post-crq/run')
      && response.request().method() === 'POST'
      && response.ok()
    ), { timeout: postCrqRunTimeoutMs }),
    executeButton.click(),
  ]);
  await page.getByRole('button', { name: /Descarregar ZIP/i }).waitFor({ state: 'visible', timeout: postCrqRunTimeoutMs });
  await verifyText(page, 'Resum executiu per lots', postCrqRunTimeoutMs);
  await expectAttachmentResponse(
    page,
    () => page.getByRole('button', { name: /Descarregar ZIP/i }).click(),
    '/api/audit/post-crq/reports',
    /auditoria_proveidors_.*\.zip/i,
  );
  await page.locator('select').nth(1).selectOption('general');
  await waitForEnabledButtonText(page, 'Descarregar resum', 60000);
  await expectAttachmentResponse(
    page,
    () => page.getByRole('button', { name: /Descarregar resum/i }).click(),
    '/api/audit/post-crq/reports',
    /report_auditoria_post_crq_general_.*\.pdf/i,
  );
  await page.locator('select').nth(1).selectOption('provider');
  const providerOptions = (await listProviderOptions(page)).filter((option) => option.value);
  if (providerOptions.length === 0) {
    if (requireProvider) {
      throw new Error(`No s'han detectat opcions provider per als esquemes Post-CRQ: ${postCrqSchemas}`);
    }
    await logStep('oracle provider report skipped: no provider options detected');
    return;
  }
  const selectedProvider = providerOptions.find((option) => option.value.toUpperCase() !== 'SENSE LOT') || providerOptions[0];
  await logStep(`oracle provider report using ${selectedProvider.value}`);
  await page.locator('select').nth(2).selectOption(selectedProvider.value);
  await waitForEnabledButtonText(page, 'Descarregar proveïdor', 60000);
  await expectAttachmentResponse(
    page,
    () => page.getByRole('button', { name: /Descarregar prove/i }).click(),
    '/api/audit/post-crq/reports',
    /report_auditoria_post_crq_provider_.*\.pdf/i,
  );
}

async function main() {
  let browser;
  let backendServer;
  let viteServer;

  try {
    const { profile, schema, postCrqSchemas, requireProvider, internalDbSource, backendEnv, viteEnv } = await prepareEnvironment();
    await logStep(`oracle internal db source ${internalDbSource}`);

    backendServer = await startServiceWithRetries(
      'oracle-backend',
      startBackendServer,
      backendEnv,
      `http://127.0.0.1:${backendPort}/api/profiles`,
      45000,
      3,
    );
    await verifyOracleProfile(profile);

    viteServer = await startServiceWithRetries(
      'oracle-vite',
      startViteServer,
      viteEnv,
      baseUrl,
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
    await runOracleSmoke(page, profile, schema, postCrqSchemas, requireProvider);
    await context.close();
    await logStep('oracle backend smoke completed');
  } finally {
    if (browser) await browser.close();
    await closeProcess(viteServer);
    await closeProcess(backendServer);
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
