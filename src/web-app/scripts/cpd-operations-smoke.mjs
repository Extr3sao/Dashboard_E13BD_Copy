import { spawn } from 'node:child_process';
import { mkdir, readFile, writeFile, rm } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const work = path.join(os.tmpdir(), 'opencode', `e13db-cpd-smoke-${Date.now()}`);
const url = 'http://127.0.0.1:18011';
await mkdir(work, { recursive: true });
const env = { ...process.env, INTERNAL_DB_PATH: path.join(work, 'internal.db'), AUTOMATION_DB_PATH: path.join(work, 'automation.db'), E13DB_BACKUP_PATH: path.join(work, 'backups'), E13DB_SCHEDULER_ENABLED: 'true', E13DB_AUTH_REQUIRED: 'true', E13DB_USER_USERNAME: 'cpd-operator', E13DB_USER_PASSWORD: 'local-fixture-password', E13DB_CPD_FIXTURE_MODE: 'true', E13DB_CPD_FIXTURE_CONTROLS: work, E13DB_DISK_WARNING_BYTES: '100', E13DB_DISK_CRITICAL_BYTES: '10', SMTP_HOST: 'fixture', SMTP_FROM_EMAIL: 'fixture@example.test', SMTP_DEFAULT_RECIPIENTS: 'operator@example.test' };
const python = process.env.E13DB_PYTHON || path.join(root, '.venv-repro/Scripts/python.exe');
let child;
let browser;
let backendLog = '';
function start() {
  child = spawn(python, ['-m', 'uvicorn', 'scripts.cpd_fixture_server:app', '--host', '127.0.0.1', '--port', '18011'], { cwd: root, env, stdio: ['ignore', 'pipe', 'pipe'] });
  child.stdout.on('data', (data) => { backendLog += data; });
  child.stderr.on('data', (data) => { backendLog += data; });
}
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
async function waitFor(check, name, seconds = 45) {
  for (let i = 0; i < seconds * 5; i++) {
    try { if (await check()) return; } catch { /* Startup may temporarily refuse connections. */ }
    if (child.exitCode !== null) throw new Error(`${name}: backend exited\n${backendLog}`);
    await sleep(200);
  }
  throw new Error(`Timeout: ${name}\n${backendLog}`);
}
async function stopHard() {
  const stopped = new Promise((resolve) => child.once('exit', resolve));
  child.kill('SIGKILL');
  await stopped;
}
function assert(condition, reason) { if (!condition) throw new Error(reason); }

try {
  start();
  await waitFor(async () => (await fetch(`${url}/ready`)).ok, 'startup readiness');
  browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto(url);
  // Authentication is real cookie + CSRF, with a fixture identity injected only
  // into this isolated process environment.
  const login = await page.request.post(`${url}/auth/login`, { data: { username: env.E13DB_USER_USERNAME, password: env.E13DB_USER_PASSWORD } });
  assert(login.ok(), 'USER login failed');
  const csrf = (await login.json()).csrf_token;
  const get = async (route) => (await page.request.get(url + route)).json();
  const post = async (route) => {
    const response = await page.request.post(url + route, { headers: { 'X-CSRF-Token': csrf } });
    assert(response.ok(), `${route}: ${await response.text()}`);
    return response.json();
  };
  await page.reload();
  await page.getByRole('button', { name: 'Operations', exact: true }).click();
  await page.getByRole('heading', { name: 'Operations', exact: true }).waitFor();
  await waitFor(async () => (await get('/api/operations/audits')).items.length > 0, 'scheduler audit and findings');
  let state = await post('/api/operations/health-check');
  assert(state.scheduler.owner && state.scheduler.running_jobs === 0, 'scheduler ownership/history missing');
  assert((await get('/api/alerting/alerts')).items.length > 0, 'alerts missing');
  const firstBackup = await post('/api/operations/backups');
  assert(firstBackup.integrity === 'PASS', 'backup failed');
  await writeFile(path.join(work, 'smtp-down'), 'down');
  const alerts = (await get('/api/alerting/alerts')).items;
  const report = await post('/api/alerting/reports/daily');
  await post(`/api/alerting/reports/${report.id}/deliver`);
  state = await post('/api/operations/health-check');
  assert(state.components['Notification Engine'].status === 'DEGRADED', 'SMTP failure was not visible');
  await page.getByRole('button', { name: 'Run health check' }).click();
  await page.getByText('Email delivery unavailable; audits and findings continue.', { exact: true }).first().waitFor();
  await page.screenshot({ path: path.join(work, 'operations-degraded.png'), fullPage: true });
  await writeFile(path.join(work, 'hold-audit'), 'hold');
  await rm(path.join(work, 'audit-started'), { force: true });
  // Trigger a real job thread through the authenticated automation API.
  const jobs = (await get('/api/automation/jobs')).items;
  await post(`/api/automation/jobs/${jobs[0].id}/run-now`);
  await waitFor(async () => !!(await readFile(path.join(work, 'audit-started'), 'utf8')), 'running audit');
  await stopHard();
  await rm(path.join(work, 'hold-audit'));
  // Accelerate only the persisted lease expiry after actual process termination.
  const expiry = spawn(python, ['-c', 'import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); c.execute("UPDATE operations_lease SET expires_at=0"); c.commit(); c.close()', env.INTERNAL_DB_PATH], { cwd: root });
  await new Promise((resolve, reject) => expiry.on('exit', (code) => code === 0 ? resolve() : reject(new Error('lease expiry fixture failed'))));
  start();
  await waitFor(async () => (await fetch(`${url}/ready`)).ok, 'restart readiness');
  const relogin = await page.request.post(`${url}/auth/login`, { data: { username: env.E13DB_USER_USERNAME, password: env.E13DB_USER_PASSWORD } });
  const newCsrf = (await relogin.json()).csrf_token;
  const recoverPost = async (route) => {
    const response = await page.request.post(url + route, { headers: { 'X-CSRF-Token': newCsrf } });
    assert(response.ok(), `${route}: ${await response.text()}`); return response.json();
  };
  state = await recoverPost('/api/operations/health-check');
  assert(state.scheduler.running_jobs === 0 && state.scheduler.failed_jobs > 0, 'orphan audit was not recovered');
  await rm(path.join(work, 'smtp-down'));
  await recoverPost(`/api/alerting/reports/${report.id}/deliver`);
  await recoverPost('/api/operations/backups');
  assert((await recoverPost('/api/operations/integrity-check')).status === 'PASS', 'recovered storage corrupt');
  state = await recoverPost('/api/operations/health-check');
  assert(state.status === 'HEALTHY', `final service state ${state.status}: ${state.reason}`);
  await page.reload();
  await page.getByText('HEALTHY', { exact: true }).first().waitFor();
  await page.getByRole('button', { name: 'Preview retention purge' }).click();
  await page.getByText('Purge preview — no changes made').waitFor();
  await page.screenshot({ path: path.join(work, 'operations-healthy.png'), fullPage: true });
  await page.getByRole('button', { name: 'Investigations', exact: true }).click();
  await page.getByRole('heading', { name: 'Investigations', exact: true }).waitFor();
  await page.getByText('SQL execution duration increased', { exact: true }).first().waitFor();
  await page.getByRole('button', { name: /SQL execution duration increased/ }).click();
  await page.getByText('FACT · PERFORMANCE', { exact: true }).first().waitFor();
  await page.getByText('Compare execution duration and workload before and after first observation.', { exact: true }).waitFor();
  await page.screenshot({ path: path.join(work, 'investigation-detail.png'), fullPage: true });
  assert(errors.length === 0, `browser errors: ${errors.join('; ')}`);
  console.log(JSON.stringify({ status: 'PASS', scenario: 'CPD failure/recovery with real HTTP, browser, scheduler and killed process', evidence: work }, null, 2));
} finally {
  if (browser) await browser.close();
  if (child && child.exitCode === null) await stopHard();
  await writeFile(path.join(work, 'backend.log'), backendLog);
}
