import { appendFile, mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';
import { installApiMocks } from './smokeApiMocks.mjs';
import { closeProcess, launchBrowser, startProcess, startServiceWithRetries } from './smokeRuntime.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(__dirname, '..');
const outputDir = path.join(projectRoot, 'output', 'playwright');
const debugLogPath = path.join(outputDir, 'smoke-debug.log');
const baseUrl = 'http://127.0.0.1:4175';
const serverShutdownState = { requested: false };
const scenario = process.argv.find((arg) => arg.startsWith('--scenario='))?.split('=')[1] || 'happy';

async function appendDebug(message) {
  await appendFile(debugLogPath, `${message}\n`, 'utf8');
}

async function logStep(message) {
  const line = `[smoke] ${message}`;
  console.log(line);
  await appendDebug(line);
}

function startViteServer() {
  serverShutdownState.requested = false;
  return process.platform === 'win32'
    ? startProcess('cmd.exe', ['/d', '/s', '/c', 'npm run preview -- --host 127.0.0.1 --port 4175 --strictPort'], {
        cwd: projectRoot,
        stdio: ['ignore', 'pipe', 'pipe'],
        windowsHide: true,
        env: { ...process.env, BROWSER: 'none' },
      }, serverShutdownState, 'Vite preview')
    : startProcess('npm', ['run', 'preview', '--', '--host', '127.0.0.1', '--port', '4175', '--strictPort'], {
        cwd: projectRoot,
        stdio: ['ignore', 'pipe', 'pipe'],
        env: { ...process.env, BROWSER: 'none' },
      }, serverShutdownState, 'Vite preview');
}

async function closeServer(child) {
  await closeProcess(child, serverShutdownState, logStep);
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

async function verifyRole(page, role, name) {
  await page.getByRole(role, { name }).waitFor({ state: 'visible', timeout: 15000 });
}

async function waitForEnabled(locator, timeoutMs = 15000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await locator.isEnabled()) {
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error('El control no s ha habilitat dins del temps esperat');
}

function normalizeDownloadFilename(filename) {
  return String(filename || '')
    .trim()
    .replace(/^[_"'`]+|[_"'`]+$/g, '');
}

async function expectDownload(page, trigger, expectedFileName) {
  const [download] = await Promise.all([
    page.waitForEvent('download', { timeout: 15000 }),
    trigger(),
  ]);
  const suggestedName = normalizeDownloadFilename(download.suggestedFilename());
  const normalizedExpectedFileName = normalizeDownloadFilename(expectedFileName);
  if (suggestedName !== normalizedExpectedFileName) {
    throw new Error(`Nom de fitxer inesperat. Esperat: ${normalizedExpectedFileName}. Rebut: ${suggestedName}`);
  }
  const downloadPath = await download.path();
  if (!downloadPath) {
    throw new Error(`No s'ha resolt cap path de descàrrega per a ${normalizedExpectedFileName}`);
  }
}

async function expectClientSideDownload(page, trigger, expectedFileName) {
  const normalizedExpectedFileName = normalizeDownloadFilename(expectedFileName);
  await trigger();
  await page.waitForFunction((value) => {
    const events = Array.isArray(window.__downloadEvents) ? window.__downloadEvents : [];
    return events.some((item) => String(item?.download || '').trim().replace(/^[_"'`]+|[_"'`]+$/g, '') === value);
  }, normalizedExpectedFileName, { timeout: 15000 });
}

async function selectPostCrqReportVariant(page, value) {
  await page.evaluate((nextValue) => {
    const select = Array.from(document.querySelectorAll('select')).find((item) => {
      const optionValues = Array.from(item.options || []).map((option) => option.value);
      return optionValues.includes('general') && optionValues.includes('provider') && optionValues.includes('all');
    });
    if (!select) {
      throw new Error('No s ha trobat el selector de variants Post-CRQ');
    }
    select.value = nextValue;
    select.dispatchEvent(new Event('input', { bubbles: true }));
    select.dispatchEvent(new Event('change', { bubbles: true }));
  }, value);
}

async function waitForDialogMessage(dialogMessages, expectedMessage, timeoutMs = 15000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (dialogMessages.includes(expectedMessage)) {
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error(`No s'ha capturat el diàleg esperat: ${expectedMessage}`);
}

async function clickSubtab(page, name) {
  await page.getByRole('button', { name }).click();
}

async function runHappySmoke(page, mocks) {
  await logStep('goto app');
  await page.goto(baseUrl, { waitUntil: 'domcontentloaded' });

  await logStep('verify shell');
  await verifyText(page, 'Oracle Audit');
  await verifyRole(page, 'button', /Ajuda: Anàlisi obsolets/i);

  await logStep('open page help');
  await page.getByRole('button', { name: /Ajuda: Anàlisi obsolets/i }).click();
  await verifyRole(page, 'dialog', /Anàlisi obsolets/i);
  await page.getByRole('button', { name: /Tanca ajuda/i }).click();

  await logStep('run deep scan');
  await page.getByPlaceholder(/Ex: MGR_APP/i).fill('APP_USER');
  await page.getByRole('button', { name: /^Auditar$/i }).click();
  await verifyText(page, 'Detalls: APP_USER');

  await logStep('post-crq subtab');
  await clickSubtab(page, 'Auditoria de canvis');
  await verifyText(page, 'Control de qualitat post-CRQ');
  await page.getByRole('button', { name: /^Tots$/i }).click();
  const runPostCrqButton = page.getByRole('button', { name: /^Executar$/i });
  await waitForEnabled(runPostCrqButton, 30000);
  await runPostCrqButton.click();
  await verifyText(page, 'Resum executiu per lots');
  await verifyText(page, 'LOT_APP');
  await expectDownload(
    page,
    () => page.getByRole('button', { name: /Descarregar ZIP/i }).click(),
    'auditoria_lots_E13DB.zip',
  );
  await expectClientSideDownload(
    page,
    () => page.getByRole('button', { name: /Descarregar consultes \(\.txt\)/i }).click(),
    'consultes_post_crq_E13DB.txt',
  );
  await selectPostCrqReportVariant(page, 'provider');
  await verifyText(page, 'LOT_APP');
  await expectDownload(
    page,
    () => page.getByRole('button', { name: /Descarregar prove/i }).click(),
    'report_post_crq_E13DB.pdf',
  );

  await logStep('automation subtab');
  await clickSubtab(page, 'Automatitzacions');
  await verifyText(page, "Programació d'auditories");
  await page.getByRole('button', { name: /^Dashboard/i }).click();
  await verifyText(page, 'Execucions');
  const analyticsMonth = await page.locator('input[type="month"]').inputValue();
  await expectClientSideDownload(
    page,
    () => page.getByRole('button', { name: /^PDF mensual$/i }).click(),
    `dashboard_automatitzacions_${analyticsMonth}.pdf`,
  );
  await page.getByRole('button', { name: /^Jobs/i }).click();
  await verifyText(page, "Jobs d'automatització");
  await verifyText(page, 'Job setmanal');

  await logStep('automation jobs lifecycle');
  const jobForm = page.locator('#job_form');
  await jobForm.locator('input').first().fill('Job smoke');
  await jobForm.getByRole('button', { name: /Crea job/i }).click();
  await verifyText(page, 'Job smoke');

  const jobsSection = page.locator('#jobs');
  const createdJobCard = jobsSection.locator('div.rounded-2xl').filter({ hasText: 'Job smoke' }).first();
  await createdJobCard.getByRole('button', { name: /^Edita$/i }).click();
  await jobForm.locator('input').first().fill('Job smoke editat');
  await jobForm.getByRole('button', { name: /Actualitza job/i }).click();
  await verifyText(page, 'Job smoke editat');

  const editedJobCard = jobsSection.locator('div.rounded-2xl').filter({ hasText: 'Job smoke editat' }).first();
  await editedJobCard.getByRole('button', { name: /Executa ara/i }).click();
  await verifyText(page, 'iniciada');
  await page.waitForTimeout(1400);

  await editedJobCard.getByRole('button', { name: /^Desactiva$/i }).click();
  await editedJobCard.getByRole('button', { name: /^Activa$/i }).waitFor({ state: 'visible', timeout: 15000 });

  await editedJobCard.getByRole('button', { name: /Esborra/i }).click();
  await page.waitForFunction((value) => !document.body.innerText.includes(value), 'Job smoke editat', { timeout: 15000 });

  await logStep('automation lots lifecycle');
  await page.getByRole('button', { name: /^Lots i mapatge/i }).click();
  await verifyText(page, 'Mapeig schema -> lot');
  const schemaMapSection = page.locator('#schema_map');
  await expectClientSideDownload(
    page,
    () => schemaMapSection.getByRole('button', { name: /Exporta CSV/i }).click(),
    'schema_lots_mapping.csv',
  );
  await schemaMapSection.getByRole('button', { name: /Afegeix/i }).click();
  const schemaInputs = schemaMapSection.getByPlaceholder('Schema Oracle');
  const lotInputs = schemaMapSection.getByPlaceholder('Lot associat');
  const schemaInputCount = await schemaInputs.count();
  await schemaInputs.nth(schemaInputCount - 1).fill('APP_USER');
  await lotInputs.nth(schemaInputCount - 1).fill('LOT_APP');
  await verifyText(page, 'Schemas duplicats: APP_USER');
  await page.waitForFunction(() => {
    const host = document.querySelector('#schema_map');
    const button = host ? Array.from(host.querySelectorAll('button')).find((item) => item.textContent?.includes('Desa mapatge')) : null;
    return Boolean(button?.disabled);
  }, { timeout: 15000 });

  await schemaInputs.nth(schemaInputCount - 1).fill('APP_STAGE');
  await lotInputs.nth(schemaInputCount - 1).fill('LOT_APP');
  await schemaMapSection.getByRole('button', { name: /Desa mapatge/i }).click();
  await verifyText(page, 'Mapeig schema -> lot desat.');
  await schemaMapSection.locator('input[value="APP_STAGE"]').waitFor({ state: 'visible', timeout: 15000 });

  const masterLotsSection = page.locator('#master_lots');
  await masterLotsSection.getByRole('button', { name: /Afegeix/i }).click();
  const masterLotCodeInputs = masterLotsSection.getByPlaceholder('Codi del lot');
  const masterLotLabelInputs = masterLotsSection.getByPlaceholder('Etiqueta');
  const masterInputCount = await masterLotCodeInputs.count();
  await masterLotCodeInputs.nth(masterInputCount - 1).fill('LOT_DATA');
  await masterLotLabelInputs.nth(masterInputCount - 1).fill('Dades');
  await masterLotsSection.getByRole('button', { name: /Desa catàleg/i }).click();
  await masterLotsSection.locator('input[placeholder="Codi del lot"][value="LOT_DATA"]').waitFor({ state: 'visible', timeout: 15000 });

  const backfillSection = page.locator('#backfill');
  await backfillSection.getByRole('button', { name: /Genera previsualitzaci/i }).click();
  await verifyText(page, 'LOT_BACKFILL');
  await backfillSection.getByRole('button', { name: /Aplica la selecció/i }).click();
  await verifyText(page, 'Backfill aplicat');
  await masterLotsSection.locator('input[placeholder="Codi del lot"][value="LOT_BACKFILL"]').waitFor({ state: 'visible', timeout: 15000 });

  await page.getByRole('button', { name: /^Dashboard/i }).click();
  await verifyText(page, 'Execucions');
  await page.getByRole('button', { name: /^Històric/i }).click();
  await verifyText(page, "Històric d'execucions");
  await verifyText(page, 'Job setmanal');
  await expectDownload(
    page,
    () => page.getByRole('link', { name: /^Informe$/i }).first().click(),
    'automation_run_77_report.pdf',
  );
  await page.getByRole('button', { name: /^Lots$/i }).click();
  await verifyText(page, 'SMTP KO');
  await expectDownload(
    page,
    () => page.getByRole('button', { name: /^CSV$/i }).click(),
    'automation_run_77_lots.csv',
  );
  await page.getByRole('button', { name: /Envia a reintents/i }).click();
  await verifyText(page, 'Element afegit a la cua de reintents.');
  await page.getByRole('button', { name: /^Reintents/i }).click();
  await verifyText(page, 'Cua de reintents');
  await verifyText(page, '2 elements');
  await verifyText(page, 'Executa');
  await page.getByRole('button', { name: /^Executa$/i }).first().click();
  await verifyText(page, 'Reintent processat.');
  await verifyText(page, 'Fet');
  await page.getByRole('button', { name: /^Destinataris/i }).click();
  const recipientsSection = page.locator('#lot_routes');
  await verifyText(page, 'app@example.com');
  await recipientsSection.getByPlaceholder('Etiqueta visible').first().fill('Aplicacions QA');
  await recipientsSection.getByPlaceholder('a@proveidor.cat, b@proveidor.cat').first().fill('qa-app@example.com');
  await recipientsSection.getByRole('button', { name: /Desa rutes/i }).click();
  await verifyText(page, 'Destinataris per lot desats.');
  await recipientsSection.locator('input[placeholder="Etiqueta visible"][value="Aplicacions QA"]').waitFor({ state: 'visible', timeout: 15000 });
  await page.waitForFunction(() => {
    const host = document.querySelector('#lot_routes');
    return Array.from(host?.querySelectorAll('textarea') || []).some((item) => item.value === 'qa-app@example.com');
  }, { timeout: 15000 });

  await page.getByRole('button', { name: /^Plantilles/i }).click();
  const templatesSection = page.locator('#templates');
  await templatesSection.locator('input[value="Assumpte"]').waitFor({ state: 'visible', timeout: 15000 });
  await verifyText(page, 'Resum TIC');
  await templatesSection.getByPlaceholder('Assumpte').first().fill('Assumpte QA');
  await templatesSection.getByPlaceholder('Cos del missatge').first().fill('Cos QA');
  await templatesSection.getByRole('button', { name: /Desa plantilles/i }).click();
  await verifyText(page, 'Plantilles desades.');
  await templatesSection.locator('input[placeholder="Assumpte"][value="Assumpte QA"]').waitFor({ state: 'visible', timeout: 15000 });
  await page.waitForFunction(() => {
    const host = document.querySelector('#templates');
    return Array.from(host?.querySelectorAll('textarea') || []).some((item) => item.value === 'Cos QA');
  }, { timeout: 15000 });

  await logStep('rules subtab');
  await clickSubtab(page, 'Tasques i regles');
  await verifyText(page, 'Regles de severitat i safata interna');

  await logStep('checks subtab');
  await clickSubtab(page, 'Gestió de controls');
  await verifyText(page, 'Gestió de controls');

  await logStep('mail config subtab');
  await clickSubtab(page, 'Configuració del servidor');
  await verifyText(page, 'Servidor de Correu (SMTP)');

  await logStep('obsolets repository subtab');
  await clickSubtab(page, "Repositori d'obsolets");
  await verifyText(page, "Registre d'Obsolets");
  const registryInputs = page.locator('input');
  await registryInputs.nth(0).fill('APP_USER');
  await registryInputs.nth(1).fill('TMP_STAGE');
  await page.locator('textarea').fill('Objecte temporal detectat a smoke test');
  await page.getByRole('button', { name: /Afegir al registre/i }).click();
  await verifyText(page, 'TMP_STAGE');

  await logStep('tutorial subtab');
  await clickSubtab(page, 'Guia i Ajuda');
  await verifyText(page, 'Tutorial');
  await verifyText(page, 'Arquitectura');

  await logStep('assert handled mocks');
  mocks.assertNoUnhandledRequests();
}

async function runErrorSmoke(page, mocks, dialogMessages) {
  await logStep('goto app');
  await page.goto(baseUrl, { waitUntil: 'domcontentloaded' });

  await logStep('post-crq error path');
  await clickSubtab(page, 'Auditoria de canvis');
  await verifyText(page, 'Control de qualitat post-CRQ');
  await page.getByRole('button', { name: /^Tots$/i }).click();
  const runPostCrqButton = page.getByRole('button', { name: /^Executar$/i });
  await waitForEnabled(runPostCrqButton, 30000);
  await runPostCrqButton.click();
  await verifyText(page, 'Fallo controlado post-CRQ');
  await page.getByRole('button', { name: /Descarregar ZIP/i }).click();
  await waitForDialogMessage(dialogMessages, 'Fallo controlado report Post-CRQ');

  await logStep('mail error path');
  await clickSubtab(page, 'Configuració del servidor');
  await verifyText(page, 'Servidor de Correu (SMTP)');
  await page.getByPlaceholder('Correu de test').fill('qa@example.com');
  await page.getByRole('button', { name: /^Test$/i }).click();
  await verifyText(page, 'Error en el test: Fallo controlado SMTP');

  await logStep('automation error paths');
  await clickSubtab(page, 'Automatitzacions');
  await verifyText(page, "Programació d'auditories");
  await page.getByRole('button', { name: /^Dashboard/i }).click();
  await verifyText(page, 'Execucions');
  await page.getByRole('button', { name: /^PDF mensual$/i }).click();
  await verifyText(page, 'Fallo controlado PDF mensual');

  await page.getByRole('button', { name: /^Històric/i }).click();
  await verifyText(page, "Històric d'execucions");
  await page.getByRole('button', { name: /^Lots$/i }).click();
  await verifyText(page, 'SMTP KO');
  await page.getByRole('button', { name: /^CSV$/i }).click();
  await verifyText(page, 'Fallo controlado export CSV');
  await page.getByRole('button', { name: /Envia a reintents/i }).click();
  await verifyText(page, 'Fallo controlado alta reintent');

  await page.getByRole('button', { name: /^Reintents/i }).click();
  await verifyText(page, 'Cua de reintents');
  await page.getByRole('button', { name: /^Executa$/i }).click();
  await verifyText(page, 'Fallo controlado reintento');

  await page.getByRole('button', { name: /^Destinataris/i }).click();
  await verifyText(page, 'app@example.com');
  await page.getByRole('button', { name: /Desa rutes/i }).click();
  await verifyText(page, 'Fallo controlado destinataris');

  await page.getByRole('button', { name: /^Plantilles/i }).click();
  await verifyText(page, 'Resum TIC');
  await page.getByRole('button', { name: /Desa plantilles/i }).click();
  await verifyText(page, 'Fallo controlado plantilles');

  await logStep('assert handled mocks');
  mocks.assertNoUnhandledRequests();
}

async function runLoadErrorSmoke(page, mocks) {
  await logStep('goto app');
  await page.goto(baseUrl, { waitUntil: 'domcontentloaded' });

  await logStep('post-crq load error path');
  await clickSubtab(page, 'Auditoria de canvis');
  await verifyText(page, 'Control de qualitat post-CRQ');
  await verifyText(page, 'Fallo controlado carga checks');

  await logStep('mail config load error path');
  await clickSubtab(page, 'Configuració del servidor');
  await verifyText(page, 'Fallo controlado carga SMTP');

  await logStep('automation load error path');
  await clickSubtab(page, 'Automatitzacions');
  await verifyText(page, "Programació d'auditories");
  await verifyText(page, 'Fallo controlado carga');
  await page.getByRole('button', { name: /^Dashboard/i }).click();
  await verifyText(page, 'Execucions');
  await page.getByRole('button', { name: /^Refresca$/i }).nth(1).click();
  await verifyText(page, 'Fallo controlado dashboard analytics');
  await page.getByRole('button', { name: /^Històric/i }).click();
  await verifyText(page, "Històric d'execucions");
  await verifyText(page, 'No hi ha execucions registrades.');
  await page.getByRole('button', { name: /^Reintents/i }).click();
  await verifyText(page, 'Cua de reintents');
  await verifyText(page, 'No hi ha reintents pendents.');

  await logStep('assert handled mocks');
  mocks.assertNoUnhandledRequests();
}

async function runProfilesErrorSmoke(page, mocks) {
  await logStep('goto app');
  await page.goto(baseUrl, { waitUntil: 'domcontentloaded' });

  await logStep('verify degraded shell');
  await verifyText(page, 'Oracle Audit');
  await verifyRole(page, 'button', /Ajuda: Anàlisi obsolets/i);
  const optionsCount = await page.locator('header.topbar select option').count();
  if (optionsCount !== 0) {
    throw new Error(`S'esperaven 0 perfils carregats i n'hi ha ${optionsCount}`);
  }

  await logStep('post-crq disabled without profiles');
  await clickSubtab(page, 'Auditoria de canvis');
  await verifyText(page, 'Control de qualitat post-CRQ');
  await page.getByRole('button', { name: /^Tots$/i }).click();
  const runButton = page.getByRole('button', { name: /^Executar$/i });
  if (!(await runButton.isDisabled())) {
    throw new Error('El botó Executar hauria d’estar deshabilitat sense perfil actiu');
  }

  await logStep('automation degraded without profiles');
  await clickSubtab(page, 'Automatitzacions');
  await verifyText(page, "Programació d'auditories");
  await verifyText(page, "Jobs d'automatització");
  await verifyText(page, 'Job setmanal');
  const automationProfileOptions = await page.locator('label:has-text("Perfil") select option').count();
  if (automationProfileOptions !== 0) {
    throw new Error(`S'esperaven 0 perfils al formulari d'automatitzacions i n'hi ha ${automationProfileOptions}`);
  }

  await logStep('assert handled mocks');
  mocks.assertNoUnhandledRequests();
}

async function runAccessibilitySmoke(page, mocks) {
  await logStep('goto app');
  await page.goto(baseUrl, { waitUntil: 'domcontentloaded' });

  await logStep('keyboard skip link');
  await page.keyboard.press('Tab');
  await page.waitForFunction(() => document.activeElement?.textContent?.includes('Salta al contingut'));
  await page.keyboard.press('Enter');
  await page.waitForFunction(() => document.activeElement?.id === 'main-content');

  await logStep('keyboard help open-close');
  const helpButton = page.getByRole('button', { name: /Ajuda: Anàlisi obsolets/i });
  await helpButton.focus();
  await page.keyboard.press('Enter');
  await verifyRole(page, 'dialog', /Anàlisi obsolets/i);
  await page.waitForFunction(() => document.activeElement?.getAttribute('aria-label') === 'Tanca ajuda');
  await page.keyboard.press('Escape');
  await page.waitForFunction(() => !document.querySelector('[role=\"dialog\"]'));
  await page.waitForFunction(() => document.activeElement?.getAttribute('aria-label')?.includes('Ajuda: Anàlisi obsolets'));

  await logStep('assert handled mocks');
  mocks.assertNoUnhandledRequests();
}

async function main() {
  await mkdir(outputDir, { recursive: true });
  await writeFile(debugLogPath, '', 'utf8');
  let server;
  let browser;
  let page;
  const consoleMessages = [];
  const pageErrors = [];
  const networkFailures = [];
  const dialogMessages = [];
  try {
    server = await startServiceWithRetries({
      label: 'mock-vite',
      startFn: () => startViteServer(),
      readyUrl: baseUrl,
      closeFn: (child) => closeServer(child),
      logStep,
      timeoutMs: 45000,
      maxAttempts: 3,
    });
    browser = await launchBrowser(logStep);
    const context = await browser.newContext({ viewport: { width: 1440, height: 1100 }, acceptDownloads: true });
    page = await context.newPage();
    await page.addInitScript(() => {
      window.__downloadEvents = [];
      const originalAnchorClick = HTMLAnchorElement.prototype.click;
      HTMLAnchorElement.prototype.click = function patchedAnchorClick(...args) {
        if (this.download) {
          window.__downloadEvents.push({ download: this.download, href: this.href });
        }
        return originalAnchorClick.apply(this, args);
      };
    });
    page.on('dialog', async (dialog) => {
      dialogMessages.push(dialog.message());
      await dialog.accept();
    });
    page.on('console', (msg) => {
      const line = `[browser:${msg.type()}] ${msg.text()}`;
      consoleMessages.push(line);
    });
    page.on('response', (response) => {
      if (response.status() >= 400) {
        networkFailures.push(`[response:${response.status()}] ${response.url()}`);
      }
    });
    page.on('requestfailed', (request) => {
      networkFailures.push(`[requestfailed] ${request.url()} :: ${request.failure()?.errorText || 'unknown'}`);
    });
    page.on('pageerror', (error) => {
      pageErrors.push(`[pageerror] ${error.stack || error.message}`);
    });

    const mocks = await installApiMocks(page, { scenario });
    if (scenario === 'error') {
      await runErrorSmoke(page, mocks, dialogMessages);
    } else if (scenario === 'load-error') {
      await runLoadErrorSmoke(page, mocks);
    } else if (scenario === 'profiles-error') {
      await runProfilesErrorSmoke(page, mocks);
    } else if (scenario === 'a11y') {
      await runAccessibilitySmoke(page, mocks);
    } else {
      await runHappySmoke(page, mocks);
    }
    await page.screenshot({ path: path.join(outputDir, `ui-smoke-${scenario}-success.png`), fullPage: true });
    await logStep('smoke success');
  } catch (error) {
    if (page) {
      await appendDebug(`[page-url] ${page.url()}`);
      await appendDebug(`[page-title] ${await page.title().catch(() => '')}`);
      await appendDebug(`[page-html] ${(await page.content().catch(() => '')).slice(0, 4000)}`);
    }
    if (consoleMessages.length > 0) {
      await appendDebug(consoleMessages.join('\n'));
    }
    if (pageErrors.length > 0) {
      await appendDebug(pageErrors.join('\\n'));
    }
    if (networkFailures.length > 0) {
      await appendDebug(networkFailures.join('\\n'));
    }
    if (browser) {
      const pages = browser.contexts().flatMap((context) => context.pages());
      if (pages[0]) {
        await pages[0].screenshot({ path: path.join(outputDir, `ui-smoke-${scenario}-error.png`), fullPage: true }).catch(() => {});
      }
    }
    console.error(error);
    await appendDebug(String(error?.stack || error));
    process.exitCode = 1;
  } finally {
    if (browser) await browser.close();
    await closeServer(server);
  }
}

main();

