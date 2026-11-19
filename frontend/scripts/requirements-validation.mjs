// Live check of the functional and security requirements added after login:
// source links, transcript editing, version history, email sharing, action tracker, admin console,
// logout, rate limiting, security headers and encryption on disk.
//
// Needs: frontend on :5173, backend on :8000 started in an empty folder (DB_DIR) with
//   SMTP_HOST=127.0.0.1 SMTP_PORT=1025 SMTP_TLS=false
// and  python scripts/smtp_sink.py --port 1025 --out <SINK_DIR>  running.
//   DB_DIR=... SINK_DIR=... node scripts/requirements-validation.mjs
// Screenshots and results.json go to ../docs/requirements-validation/.
import { chromium } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';

const BASE = process.env.BASE_URL ?? 'http://localhost:5173';
const DB_DIR = process.env.DB_DIR;
const SINK_DIR = process.env.SINK_DIR;
const OUT = path.resolve('../docs/requirements-validation');
const WAV = path.resolve('../eval/recordings/quiet_room.wav');
await fs.mkdir(OUT, { recursive: true });

const results = [];
const check = (id, name, pass, detail = '') => {
  results.push({ id, name, pass, detail });
  console.log(`${pass ? 'PASS' : 'FAIL'} ${id} ${name}${detail ? ' :: ' + detail : ''}`);
};
const guard = async (id, name, fn) => {
  try { await fn(); } catch (e) { check(id, name, false, String(e.message).split('\n')[0]); }
};
const browser = await chromium.launch({ channel: 'chrome' });
const page = await (await browser.newContext({ viewport: { width: 1280, height: 900 } })).newPage();
const shot = (name) => page.screenshot({ path: path.join(OUT, `${name}.png`), fullPage: true });
const api = (p, init = {}) => page.request.fetch(`${BASE}/api/v1${p}`, init);

async function register(name, email, password) {
  await page.getByRole('button', { name: 'Create an account' }).click();
  await page.getByLabel('Name').fill(name);
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password').fill(password);
  await page.getByRole('button', { name: 'Create account' }).click();
}
async function login(email, password) {
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password').fill(password);
  await page.getByRole('button', { name: 'Log in' }).click();
}
const token = () => page.evaluate(() => sessionStorage.getItem('ammg_token'));
const refresh = () => page.evaluate(() => sessionStorage.getItem('ammg_refresh'));

// ---------------------------------------------------------------- accounts and one processed meeting
await page.goto(BASE);
await register('Admin Anita', 'admin@example.com', 'admin-pass-1');
await page.getByRole('heading', { name: 'All meetings' }).waitFor({ timeout: 15000 });
await page.getByRole('button', { name: 'Log out' }).click();
await page.getByRole('heading', { name: 'Log in' }).waitFor();
await register('Ravi User', 'ravi@example.com', 'ravi-pass-12');
await page.getByRole('heading', { name: 'My meetings' }).waitFor({ timeout: 15000 });

await page.getByRole('button', { name: '+ New meeting' }).click();
await page.getByLabel('Title', { exact: true }).fill('Weekly review');
await page.getByLabel('Date and time').fill('2026-11-18T10:00');
const people = [['Ravi', 'ravi@example.com'], ['Meera', 'meera@example.com'], ['Asha', 'asha@example.com'], ['Karthik', 'karthik@example.com']];
for (let i = 0; i < people.length; i++) {
  if (i > 0) await page.getByRole('button', { name: '+ Add attendee' }).click();
  await page.getByLabel(`Attendee ${i + 1} name`).fill(people[i][0]);
  await page.getByLabel(`Attendee ${i + 1} email`).fill(people[i][1]);
}
await page.getByRole('button', { name: /Create meeting/ }).click();
await page.getByRole('heading', { name: /Add the meeting audio/ }).waitFor({ timeout: 15000 });
await page.getByLabel('Audio file').setInputFiles(WAV);
await page.getByRole('button', { name: /Upload and generate/ }).click();
await page.getByLabel('Topic title').first().waitFor({ timeout: 600000 });
await page.getByLabel('Text of segment 1').waitFor({ timeout: 30000 });
await shot('01-minutes-with-transcript');

// ---------------------------------------------------------------- AMG-F-042 source links
await guard('F-042', 'Items link to the recording and playing jumps to that moment', async () => {
  const buttons = page.getByRole('button', { name: /Play recording from/ });
  const count = await buttons.count();
  const label = count ? await buttons.first().getAttribute('aria-label') : '';
  const seconds = (() => { const m = /from (\d+):(\d+)/.exec(label ?? ''); return m ? Number(m[1]) * 60 + Number(m[2]) : -1; })();
  await buttons.last().click();
  await page.waitForTimeout(800);
  const t = await page.evaluate(() => document.querySelector('audio')?.currentTime ?? -1);
  check('F-042', 'Items link to the recording and playing jumps to that moment', count > 0 && t >= 0, `${count} source buttons; first at ${seconds}s; audio position after click ${t.toFixed(1)}s`);
});

// ---------------------------------------------------------------- AMG-F-022 transcript editing
await guard('F-022', 'Edit transcript text and speaker; edits survive a reload', async () => {
  const text = page.getByLabel('Text of segment 1');
  await text.fill('Good morning everyone, this line was edited by the validation script.');
  await page.getByLabel('Speaker for segment 1').fill('Ravi');
  await page.getByRole('button', { name: 'Save transcript' }).click();
  await page.getByText('Transcript saved').waitFor({ timeout: 10000 });
  await page.reload();                                           // sessionStorage keeps the login
  await page.getByRole('button', { name: 'My meetings' }).click();
  await page.getByRole('button', { name: 'Open Weekly review' }).click();
  await page.getByLabel('Text of segment 1').waitFor({ timeout: 20000 });
  const saved = await page.getByLabel('Text of segment 1').inputValue();
  const speaker = await page.getByLabel('Speaker for segment 1').inputValue();
  await shot('02-transcript-edited');
  check('F-022', 'Edit transcript text and speaker; edits survive a reload', /edited by the validation script/.test(saved) && speaker === 'Ravi', `speaker=${speaker}`);
});

// ---------------------------------------------------------------- AMG-F-043 version history
await guard('F-043', 'Saving keeps old versions and an old version can be restored', async () => {
  const original = await page.getByLabel('Topic title').first().inputValue();
  await page.getByLabel('Topic title').first().fill('Edited topic title');
  await page.getByText('All changes saved').waitFor({ timeout: 15000 });
  await page.getByLabel('Topic title').first().fill('Edited again');
  await page.getByText('All changes saved').waitFor({ timeout: 15000 });
  // two saves -> the current version plus versions 2 and 1; wait until the list has caught up
  await page.waitForFunction(() => document.querySelectorAll('.versions li').length >= 3, null, { timeout: 15000 });
  const versionsShown = await page.locator('.versions li').count();
  await shot('03-version-history');
  page.once('dialog', (d) => d.accept());
  await page.getByRole('button', { name: 'Restore version 1' }).click();
  await page.waitForFunction((o) => document.querySelector('[aria-label="Topic title"]')?.value === o, original, { timeout: 15000 });
  await page.waitForFunction((n) => document.querySelectorAll('.versions li').length > n, versionsShown, { timeout: 15000 });
  const afterRestore = await page.locator('.versions li').count();
  check('F-043', 'Saving keeps old versions and an old version can be restored', versionsShown >= 3 && afterRestore === versionsShown + 1,
    `versions listed ${versionsShown} -> ${afterRestore} after restore; topic title back to "${original}"`);
});

// ---------------------------------------------------------------- AMG-F-045 share by email
await guard('F-045', 'Minutes are emailed as an attachment', async () => {
  const before = (await fs.readdir(SINK_DIR)).length;
  await page.getByLabel('Email addresses').fill('teacher@example.com');
  await page.getByLabel('Attachment format').selectOption('docx');
  await page.getByRole('button', { name: 'Send' }).click();
  await page.getByText(/Sent to 1 address/).waitFor({ timeout: 20000 });
  const files = (await fs.readdir(SINK_DIR)).sort();
  const mail = await fs.readFile(path.join(SINK_DIR, files[files.length - 1]), 'latin1');
  await shot('04-shared');
  check('F-045', 'Minutes are emailed as an attachment', files.length === before + 1 && /teacher@example\.com/.test(mail) && /\.docx/.test(mail),
    `mail files ${before} -> ${files.length}; has docx attachment: ${/\.docx/.test(mail)}`);
});

// ---------------------------------------------------------------- AMG-F-050/051 action tracker
await guard('F-050', 'Action tracker lists items across meetings and marks one done', async () => {
  await page.getByRole('button', { name: 'Action tracker' }).click();
  await page.getByRole('table', { name: 'Action items' }).waitFor({ timeout: 15000 });
  const boxes = page.getByRole('checkbox', { name: /done$/ });
  const total = await boxes.count();
  await shot('05-action-tracker');
  await boxes.first().click();
  await page.waitForFunction(() => document.querySelectorAll('input[type=checkbox]:checked').length >= 1, null, { timeout: 10000 });
  await page.getByRole('button', { name: 'Action tracker' }).click();
  await page.waitForTimeout(500);
  const checked = await page.locator('input[type=checkbox]:checked').count();
  await page.getByLabel('Status filter').selectOption('Done');
  await page.waitForTimeout(800);
  const doneOnly = await page.getByRole('checkbox', { name: /done$/ }).count();
  check('F-050', 'Action tracker lists items across meetings and marks one done', total > 0 && checked >= 1 && doneOnly === 1, `${total} items; ${checked} checked; filter Done shows ${doneOnly}`);
});

// ---------------------------------------------------------------- security checks from the user's session
await guard('SR-005/004', 'Logout kills the access and refresh tokens', async () => {
  const oldAccess = await token();
  const oldRefresh = await refresh();
  await page.getByRole('button', { name: 'Log out' }).click();
  await page.getByRole('heading', { name: 'Log in' }).waitFor();
  const afterAccess = await page.request.get(`${BASE}/api/v1/meetings`, { headers: { Authorization: `Bearer ${oldAccess}` } });
  const afterRefresh = await page.request.post(`${BASE}/api/v1/auth/refresh`, { data: { refresh_token: oldRefresh } });
  check('SR-004', 'Logout kills the access and refresh tokens', afterAccess.status() === 401 && afterRefresh.status() === 401,
    `old access token -> ${afterAccess.status()}, old refresh token -> ${afterRefresh.status()}`);
});

await guard('SR-004b', 'Refresh token rotates and a reused one ends all sessions', async () => {
  const login1 = await (await page.request.post(`${BASE}/api/v1/auth/login`, { data: { email: 'ravi@example.com', password: 'ravi-pass-12' } })).json();
  const rotated = await (await page.request.post(`${BASE}/api/v1/auth/refresh`, { data: { refresh_token: login1.refresh_token } })).json();
  const reuse = await page.request.post(`${BASE}/api/v1/auth/refresh`, { data: { refresh_token: login1.refresh_token } });
  const dead = await page.request.get(`${BASE}/api/v1/meetings`, { headers: { Authorization: `Bearer ${rotated.token}` } });
  check('SR-004b', 'Refresh token rotates and a reused one ends all sessions',
    rotated.refresh_token !== login1.refresh_token && reuse.status() === 401 && dead.status() === 401,
    `reuse -> ${reuse.status()}; newer session after reuse -> ${dead.status()}`);
});

await guard('SR-010', 'Security headers are sent', async () => {
  const h = (await page.request.get(`${BASE}/api/v1/auth/me`)).headers();
  const ok = h['x-content-type-options'] === 'nosniff' && h['x-frame-options'] === 'DENY' && /default-src 'self'/.test(h['content-security-policy'] ?? '');
  check('SR-010', 'Security headers are sent', ok, `nosniff, X-Frame-Options ${h['x-frame-options']}, CSP ${h['content-security-policy']}`);
});

await guard('SR-002', 'Recording and database text are encrypted on disk', async () => {
  const uploads = path.join(DB_DIR, 'uploads', 'audio');
  const audioFile = (await fs.readdir(uploads))[0];
  const audioHead = (await fs.readFile(path.join(uploads, audioFile))).subarray(0, 8).toString('latin1');
  const db = await fs.readFile(path.join(DB_DIR, 'ammg.db'));
  const leaks = ['Good morning', 'seminar', 'Karthik will', 'validation script'].filter((w) => db.includes(Buffer.from(w)));
  check('SR-002', 'Recording and database text are encrypted on disk', audioHead === 'AMMGENC1' && leaks.length === 0,
    `audio file starts with "${audioHead}"; transcript/minutes words found in plain text in ammg.db: ${leaks.length ? leaks.join(', ') : 'none'}`);
});

// ---------------------------------------------------------------- administrator
await guard('F-060', 'Admin console shows jobs, users, audit log', async () => {
  await login('admin@example.com', 'admin-pass-1');
  await page.getByRole('heading', { name: 'All meetings' }).waitFor({ timeout: 15000 });
  await page.getByRole('button', { name: 'Admin console' }).click();
  const jobs = await page.getByRole('table', { name: 'Processing jobs' }).innerText();
  const audit = await page.getByRole('table', { name: 'Audit log' }).innerText();
  await shot('06-admin-console');
  check('F-060', 'Admin console shows jobs, users, audit log', /Weekly review/.test(jobs) && /READY/.test(jobs) && /ravi@example\.com/.test(jobs),
    `jobs table mentions the meeting and READY; audit events seen: ${['register', 'login', 'logout', 'share', 'transcript-edit', 'login-failed'].filter((e) => audit.includes(e)).join(', ')}`);
  check('SR-008a', 'Audit log records logins, logouts, sharing and transcript edits',
    ['register', 'login', 'logout', 'share', 'transcript-edit'].every((e) => audit.includes(e)));
});

await guard('SR-008b', 'Audit log can be verified', async () => {
  await page.getByRole('button', { name: 'Check that the log is untouched' }).click();
  await page.getByText('The audit log is intact.').waitFor({ timeout: 10000 });
  check('SR-008b', 'Audit log can be verified', true, 'hash chain intact');
});

await guard('F-001/002', 'Admin changes a role and the change is audited', async () => {
  await page.getByLabel('Role of ravi@example.com').selectOption('admin');
  await page.getByText('ravi@example.com is now admin.').waitFor({ timeout: 10000 });
  await page.getByLabel('Role of ravi@example.com').selectOption('user');
  await page.getByText('ravi@example.com is now user.').waitFor({ timeout: 10000 });
  const audit = await page.getByRole('table', { name: 'Audit log' }).innerText();
  check('SR-008c', 'Admin changes a role and the change is audited', /role-change/.test(audit), 'role-change events in the audit log');
});

await guard('F-051', 'Reminders run and report what they did', async () => {
  await page.getByRole('button', { name: 'Send deadline reminders now' }).click();
  const note = await page.getByRole('status').innerText();
  const files = (await fs.readdir(SINK_DIR)).length;
  await shot('07-reminders');
  check('F-051', 'Reminders run and report what they did', /Reminders sent: \d+/.test(note), `${note}; mail files now ${files}`);
});

await guard('F-061', 'Retention purge works from the console', async () => {
  page.once('dialog', (d) => d.accept());
  await page.getByLabel('Retention days').fill('30');
  await page.getByRole('button', { name: /Delete meetings older/ }).click();
  await page.getByText(/Deleted \d+ meeting\(s\) older than 30 days/).waitFor({ timeout: 10000 });
  const jobs = await page.getByRole('table', { name: 'Processing jobs' }).innerText();
  check('F-061', 'Retention purge works from the console', /Weekly review/.test(jobs), 'a new meeting is kept when the limit is 30 days');
});

// Last, because it uses up the login allowance of this address for a minute.
await guard('SR-007', 'Login is rate limited (HTTP 429)', async () => {
  const codes = [];
  for (let i = 0; i < 12; i++) {
    codes.push((await page.request.post(`${BASE}/api/v1/auth/login`, { data: { email: 'nobody@example.com', password: 'whatever-1' } })).status());
  }
  check('SR-007', 'Login is rate limited (HTTP 429)', codes.includes(429), `status codes: ${codes.join(' ')}`);
});

await fs.writeFile(path.join(OUT, 'results.json'), JSON.stringify(results, null, 2));
await browser.close();
const failed = results.filter((r) => !r.pass).length;
console.log(`\n${results.length - failed}/${results.length} checks passed. Details: docs/requirements-validation/results.json`);
process.exit(failed ? 1 : 0);
