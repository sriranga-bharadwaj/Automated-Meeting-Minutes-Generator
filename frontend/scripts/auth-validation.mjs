// Live check of login, roles, the meeting list and upload-time audio validation.
// Needs the backend on :8000 (ideally started in an empty folder so its database is new) and
// the frontend on :5173:   node scripts/auth-validation.mjs
// Screenshots and results.json go to ../docs/auth-validation/.
import { chromium } from '@playwright/test';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';

const BASE = process.env.BASE_URL ?? 'http://localhost:5173';
const OUT = path.resolve('../docs/auth-validation');
const WAV = path.resolve('../eval/recordings/quiet_room.wav');
await fs.mkdir(OUT, { recursive: true });

const results = [];
const check = (id, name, pass, detail = '') => {
  results.push({ id, name, pass, detail });
  console.log(`${pass ? 'PASS' : 'FAIL'} ${id} ${name}${detail ? ' :: ' + detail : ''}`);
};
const browser = await chromium.launch({ channel: 'chrome' });

async function newPage() {
  const page = await (await browser.newContext({ viewport: { width: 1280, height: 800 } })).newPage();
  await page.goto(BASE);
  return page;
}
const shot = (page, name) => page.screenshot({ path: path.join(OUT, `${name}.png`), fullPage: true });

async function register(page, name, email, password) {
  await page.getByRole('button', { name: 'Create an account' }).click();
  await page.getByLabel('Name').fill(name);
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password').fill(password);
  await page.getByRole('button', { name: 'Create account' }).click();
}
async function login(page, email, password) {
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password').fill(password);
  await page.getByRole('button', { name: 'Log in' }).click();
}

// ---- 1. the login page is the first thing a visitor sees
let page = await newPage();
try {
  await page.getByRole('heading', { name: 'Log in' }).waitFor({ timeout: 10000 });
  await shot(page, '01-login');
  check('AUTH-01', 'Visitor sees the login page first', true);
} catch (e) { check('AUTH-01', 'Visitor sees the login page first', false, e.message.split('\n')[0]); }

// ---- 2. validation: an email without @ is explained, nothing is sent
try {
  await page.getByLabel('Email').fill('Aasha35gmail.com');
  await page.getByLabel('Password').fill('password123');
  await page.getByRole('button', { name: 'Log in' }).click();
  await page.getByText(/Enter a valid email address/).waitFor({ timeout: 5000 });
  await shot(page, '02-login-bad-email');
  check('AUTH-02', 'Email without @ is rejected with an explanation', true);
} catch (e) { check('AUTH-02', 'Email without @ is rejected with an explanation', false, e.message.split('\n')[0]); }

// ---- 3. first account becomes the administrator
try {
  await page.reload();
  await register(page, 'Admin Anita', 'admin@example.com', 'admin-pass-1');
  await page.getByRole('heading', { name: 'All meetings' }).waitFor({ timeout: 15000 });
  const role = await page.locator('.pill.role').innerText();
  await shot(page, '03-admin-empty-list');
  check('AUTH-03', 'First registered account is an administrator', role.toLowerCase() === 'admin', `role shown: ${role}`);
} catch (e) { check('AUTH-03', 'First registered account is an administrator', false, e.message.split('\n')[0]); }
await page.getByRole('button', { name: 'Log out' }).click();

// ---- 4. wrong password message
try {
  await page.getByRole('heading', { name: 'Log in' }).waitFor();
  await login(page, 'admin@example.com', 'not-the-password');
  const alert = await page.getByRole('alert').innerText();
  await shot(page, '04-wrong-password');
  check('AUTH-04', 'Wrong password shows "Email or password is wrong."', /wrong/i.test(alert), alert);
} catch (e) { check('AUTH-04', 'Wrong password shows an error', false, e.message.split('\n')[0]); }

// ---- 5. second account is a normal user; full flow: create, upload, minutes, title kept
await page.reload();
try {
  await register(page, 'Ravi User', 'ravi@example.com', 'ravi-pass-12');
  await page.getByRole('heading', { name: 'My meetings' }).waitFor({ timeout: 15000 });
  const role = await page.locator('.pill.role').innerText();
  await shot(page, '05-user-empty-list');
  check('AUTH-05', 'Second account is a normal user with "My meetings"', role.toLowerCase() === 'user', `role shown: ${role}`);
} catch (e) { check('AUTH-05', 'Second account is a normal user', false, e.message.split('\n')[0]); }

try {
  await page.getByRole('button', { name: '+ New meeting' }).click();
  await page.getByLabel('Title', { exact: true }).fill('Database discussion');
  await page.getByLabel('Date and time').fill('2026-11-19T15:00');
  await page.getByLabel('Attendee 1 name').fill('Ravi');
  await page.getByLabel('Attendee 1 email').fill('ravi@example.com');
  await page.getByRole('button', { name: /Create meeting/ }).click();
  await page.getByRole('heading', { name: /Add the meeting audio/ }).waitFor({ timeout: 15000 });

  // corrupt file is refused at upload time, with a plain message
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'ammg-auth-'));
  const bad = path.join(dir, 'corrupt.mp3');
  await fs.writeFile(bad, 'plain text, not audio');
  await page.getByLabel('Audio file').setInputFiles(bad);
  await page.getByRole('button', { name: /Upload and generate/ }).click();
  const msg = await page.getByRole('alert').first().innerText();
  await shot(page, '06-corrupt-refused-at-upload');
  check('UPLOAD-01', 'Corrupt .mp3 is refused at upload with a plain message',
    /could not be read as audio/i.test(msg) && !/ffmpeg|Error opening/i.test(msg), msg);

  await page.getByLabel('Audio file').setInputFiles(WAV);
  await page.getByRole('button', { name: /Upload and generate/ }).click();
  await page.getByLabel('Topic title').first().waitFor({ timeout: 600000 });
  const title = await page.getByRole('heading', { level: 2 }).first().innerText();
  await shot(page, '07-minutes');
  check('TITLE-01', 'Minutes show the title the user typed', title === 'Database discussion', `heading: ${title}`);
} catch (e) { check('FLOW-01', 'Create, upload, minutes', false, e.message.split('\n')[0]); }

// ---- 6. the list shows the meeting; the user cannot see other users' meetings
try {
  await page.getByRole('button', { name: 'My meetings' }).click();
  await page.getByRole('table', { name: 'Meetings' }).waitFor({ timeout: 10000 });
  const text = await page.getByRole('table', { name: 'Meetings' }).innerText();
  await shot(page, '08-user-list');
  check('LIST-01', 'Meeting list shows the meeting as "Minutes ready"', /Database discussion/.test(text) && /Minutes ready/.test(text));
  check('LIST-02', 'Normal user sees no Owner column', !/Owner/.test(text));
} catch (e) { check('LIST-01', 'Meeting list shows the meeting', false, e.message.split('\n')[0]); }

// reopen from the list
try {
  await page.getByRole('button', { name: 'Open Database discussion' }).click();
  await page.getByLabel('Topic title').first().waitFor({ timeout: 15000 });
  check('LIST-03', 'Open from the list shows the saved minutes', true);
} catch (e) { check('LIST-03', 'Open from the list shows the saved minutes', false, e.message.split('\n')[0]); }

// the API refuses a token for a different account's meeting
try {
  const meetingToken = await page.evaluate(() => sessionStorage.getItem('ammg_token'));
  const list = await (await page.request.get(`${BASE}/api/v1/meetings`, { headers: { Authorization: `Bearer ${meetingToken}` } })).json();
  const meetingId = list[0].id;
  const other = await page.request.post(`${BASE}/api/v1/auth/register`, { data: { name: 'Eve', email: 'eve@example.com', password: 'eve-pass-123' } });
  const eveToken = (await other.json()).token;
  const denied = await page.request.get(`${BASE}/api/v1/meetings/${meetingId}/minutes`, { headers: { Authorization: `Bearer ${eveToken}` } });
  const anon = await page.request.get(`${BASE}/api/v1/meetings`);
  check('ROLE-01', "Another user gets 403 for Ravi's meeting", denied.status() === 403, `status ${denied.status()}`);
  check('ROLE-02', 'No token gets 401', anon.status() === 401, `status ${anon.status()}`);
} catch (e) { check('ROLE-01', 'Access control over the API', false, e.message.split('\n')[0]); }

// ---- 7. administrator sees everything and the user list
await page.getByRole('button', { name: 'Log out' }).click();
try {
  await page.getByRole('heading', { name: 'Log in' }).waitFor();
  await login(page, 'admin@example.com', 'admin-pass-1');
  await page.getByRole('heading', { name: 'All meetings' }).waitFor({ timeout: 15000 });
  const table = await page.getByRole('table', { name: 'Meetings' }).innerText();
  await page.getByRole('table', { name: 'Users' }).waitFor({ timeout: 10000 });
  await shot(page, '09-admin-list');
  check('ADMIN-01', "Administrator sees Ravi's meeting with the owner's email",
    /Database discussion/.test(table) && /ravi@example.com/.test(table));
  check('ADMIN-02', 'Administrator sees the user list', true);
} catch (e) { check('ADMIN-01', 'Administrator view', false, e.message.split('\n')[0]); }

// ---- 8. delete
try {
  page.once('dialog', (d) => d.accept());
  await page.getByRole('button', { name: 'Delete Database discussion' }).click();
  await page.getByText(/No meetings yet/).waitFor({ timeout: 10000 });
  await shot(page, '10-after-delete');
  check('DEL-01', 'Administrator can delete a meeting', true);
} catch (e) { check('DEL-01', 'Administrator can delete a meeting', false, e.message.split('\n')[0]); }

await fs.writeFile(path.join(OUT, 'results.json'), JSON.stringify(results, null, 2));
await browser.close();
const failed = results.filter((r) => !r.pass).length;
console.log(`\n${results.length - failed}/${results.length} checks passed. Details: docs/auth-validation/results.json`);
process.exit(failed ? 1 : 0);
