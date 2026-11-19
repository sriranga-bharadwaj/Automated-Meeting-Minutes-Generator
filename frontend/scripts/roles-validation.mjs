// Live check of AMG-F-002: roles Admin, Organizer, Participant and access to invited meetings.
// Needs the backend on :8000 (started in an empty folder) and the frontend on :5173:
//   node scripts/roles-validation.mjs
// Screenshots and results.json go to ../docs/roles-validation/.
import { chromium } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';

const BASE = process.env.BASE_URL ?? 'http://localhost:5173';
const OUT = path.resolve('../docs/roles-validation');
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
async function newPage() {
  const page = await (await browser.newContext({ viewport: { width: 1280, height: 900 } })).newPage();
  await page.goto(BASE);
  return page;
}
const shot = (page, name) => page.screenshot({ path: path.join(OUT, `${name}.png`), fullPage: true });
const token = (page) => page.evaluate(() => sessionStorage.getItem('ammg_token'));
async function register(page, name, email) {
  await page.getByRole('button', { name: 'Create an account' }).click();
  await page.getByLabel('Name').fill(name);
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password').fill('password-123');
  await page.getByRole('button', { name: 'Create account' }).click();
}
async function login(page, email) {
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password').fill('password-123');
  await page.getByRole('button', { name: 'Log in' }).click();
}
const call = (page, method, url, tok, data) =>
  page.request.fetch(`${BASE}/api/v1${url}`, { method, headers: { Authorization: `Bearer ${tok}` }, data });

// ------------------------------------------------------------ accounts: admin, organizer Olive, participant Pat, stranger Sam
const admin = await newPage();
await register(admin, 'Admin Anita', 'admin@example.com');
await admin.getByRole('heading', { name: 'All meetings' }).waitFor({ timeout: 15000 });
const adminRole = (await admin.locator('.pill.role').innerText()).toLowerCase();
check('ROLE-01', 'First account is the administrator', adminRole === 'admin', `role shown: ${adminRole}`);

const olive = await newPage();
await register(olive, 'Olive Organizer', 'olive@example.com');
await olive.getByRole('heading', { name: 'My meetings' }).waitFor({ timeout: 15000 });
const oliveRole = (await olive.locator('.pill.role').innerText()).toLowerCase();
check('ROLE-02', 'Later accounts are organizers', oliveRole === 'organizer', `role shown: ${oliveRole}`);

const pat = await newPage();
await register(pat, 'Pat Participant', 'pat@example.com');
await pat.getByRole('heading', { name: 'My meetings' }).waitFor({ timeout: 15000 });

const sam = await newPage();
await register(sam, 'Sam Stranger', 'sam@example.com');
await sam.getByRole('heading', { name: 'My meetings' }).waitFor({ timeout: 15000 });

// ------------------------------------------------------------ the administrator makes Pat a participant
await guard('ROLE-03', 'Admin sets Pat to participant', async () => {
  await admin.getByRole('button', { name: 'Admin console' }).click();
  await admin.getByLabel('Role of pat@example.com').selectOption('participant');
  await admin.getByText('pat@example.com is now participant.').waitFor({ timeout: 10000 });
  await shot(admin, '01-admin-sets-participant');
  const options = await admin.getByLabel('Role of pat@example.com').locator('option').allInnerTexts();
  check('ROLE-03', 'Admin sets Pat to participant', options.join(',') === 'admin,organizer,participant', `role choices: ${options.join(', ')}`);
});

// ------------------------------------------------------------ Olive creates a meeting and invites Pat by email
await guard('MEET-01', 'Organizer creates a meeting, invites Pat, and the minutes are made', async () => {
  await olive.getByRole('button', { name: '+ New meeting' }).click();
  await olive.getByLabel('Title', { exact: true }).fill('Budget review');
  await olive.getByLabel('Date and time').fill('2026-11-18T10:00');
  await olive.getByLabel('Attendee 1 name').fill('Olive');
  await olive.getByLabel('Attendee 1 email').fill('olive@example.com');
  await olive.getByRole('button', { name: '+ Add attendee' }).click();
  await olive.getByLabel('Attendee 2 name').fill('Pat');
  await olive.getByLabel('Attendee 2 email').fill('Pat@Example.com');       // capital letters on purpose
  await olive.getByRole('button', { name: /Create meeting/ }).click();
  await olive.getByRole('heading', { name: /Add the meeting audio/ }).waitFor({ timeout: 15000 });
  await olive.getByLabel('Audio file').setInputFiles(WAV);
  await olive.getByRole('button', { name: /Upload and generate/ }).click();
  await olive.getByLabel('Topic title').first().waitFor({ timeout: 600000 });
  await shot(olive, '02-organizer-minutes');
  check('MEET-01', 'Organizer creates a meeting, invites Pat, and the minutes are made', true);
});

// ------------------------------------------------------------ Pat (participant) sees it, read only
await guard('PART-01', 'Participant sees the shared meeting and cannot create meetings', async () => {
  await pat.reload();
  await pat.getByRole('heading', { name: 'Meetings shared with me' }).waitFor({ timeout: 15000 });
  const newButton = await pat.getByRole('button', { name: '+ New meeting' }).count();
  const row = await pat.getByRole('table', { name: 'Meetings' }).innerText();
  const deleteButtons = await pat.getByRole('button', { name: /^Delete/ }).count();
  await shot(pat, '03-participant-list');
  check('PART-01', 'Participant sees the shared meeting and cannot create meetings',
    newButton === 0 && deleteButtons === 0 && /Budget review/.test(row) && /Invited/.test(row) && /olive@example\.com/.test(row),
    `New meeting buttons: ${newButton}; Delete buttons: ${deleteButtons}; row: ${row.replace(/\s+/g, ' ').slice(0, 90)}`);
});

await guard('PART-02', 'Participant opens the minutes read only', async () => {
  await pat.getByRole('button', { name: 'Open Budget review' }).click();
  await pat.getByText(/You were invited to this meeting/).waitFor({ timeout: 20000 });
  const topicDisabled = await pat.getByLabel('Topic title').first().isDisabled();
  const addDisabled = await pat.getByRole('button', { name: '+ Add topic' }).isDisabled();
  const shareShown = await pat.getByRole('region', { name: 'Share by email' }).count();
  const newMeeting = await pat.getByRole('button', { name: 'Start a new meeting' }).count();
  await pat.getByLabel('Text of segment 1').waitFor({ timeout: 20000 });
  const transcriptReadOnly = await pat.getByLabel('Text of segment 1').getAttribute('readonly');
  const saveShown = await pat.getByRole('button', { name: 'Save transcript' }).count();
  const topicReadOnly = (await pat.getByLabel('Topic title').first().getAttribute('readonly')) !== null;
  const playButtons = pat.getByRole('button', { name: /Play recording from/ });
  const sources = await playButtons.count();
  let enabledPlay = 0;
  for (let i = 0; i < sources; i++) if (await playButtons.nth(i).isEnabled()) enabledPlay++;
  await playButtons.last().click();                                   // listening is allowed
  await pat.waitForTimeout(800);
  const position = await pat.evaluate(() => document.querySelector('audio')?.currentTime ?? -1);
  const exportEnabled = await pat.getByRole('button', { name: 'Markdown', exact: true }).isEnabled();
  await shot(pat, '04-participant-read-only-minutes');
  check('PART-02', 'Participant opens the minutes read only',
    topicReadOnly && addDisabled && shareShown === 0 && newMeeting === 0 && transcriptReadOnly !== null && saveShown === 0
      && sources > 0 && enabledPlay === sources && position > 0 && exportEnabled,
    `fields read only: ${topicReadOnly}; share hidden: ${shareShown === 0}; transcript read only: ${transcriptReadOnly !== null}; ` +
    `play buttons enabled: ${enabledPlay}/${sources}; audio position after click: ${position.toFixed(1)}s; export enabled: ${exportEnabled}`);
});

await guard('PART-03', 'Participant can export the minutes', async () => {
  const download = pat.waitForEvent('download', { timeout: 30000 });
  await pat.getByRole('button', { name: 'Markdown', exact: true }).click();
  const file = await download;
  check('PART-03', 'Participant can export the minutes', file.suggestedFilename().endsWith('.md'), file.suggestedFilename());
});

// ------------------------------------------------------------ the server enforces it (not just the screen)
await guard('API-01', 'Server refuses writes by an invited person and meeting creation by a participant', async () => {
  const patTok = await token(pat);
  const oliveTok = await token(olive);
  const list = await (await call(olive, 'GET', '/meetings', oliveTok)).json();
  const id = list.find((m) => m.title === 'Budget review').id;
  const minutes = await (await call(pat, 'GET', `/meetings/${id}/minutes`, patTok)).json();
  const codes = {
    read: (await call(pat, 'GET', `/meetings/${id}/minutes`, patTok)).status(),
    saveMinutes: (await call(pat, 'PUT', `/meetings/${id}/minutes`, patTok, { content: minutes })).status(),
    share: (await call(pat, 'POST', `/meetings/${id}/share`, patTok, { emails: ['a@b.com'] })).status(),
    del: (await call(pat, 'DELETE', `/meetings/${id}`, patTok)).status(),
    create: (await call(pat, 'POST', '/meetings', patTok, { title: 'Sneaky' })).status(),
  };
  const ok = codes.read === 200 && codes.saveMinutes === 403 && codes.share === 403 && codes.del === 403 && codes.create === 403;
  check('API-01', 'Server refuses writes by an invited person and meeting creation by a participant', ok, JSON.stringify(codes));
});

await guard('STR-01', 'An uninvited person sees nothing and gets 403', async () => {
  const samTok = await token(sam);
  const oliveTok = await token(olive);
  const id = (await (await call(olive, 'GET', '/meetings', oliveTok)).json())[0].id;
  const mine = await (await call(sam, 'GET', '/meetings', samTok)).json();
  const direct = await call(sam, 'GET', `/meetings/${id}/minutes`, samTok);
  await sam.reload();
  await sam.getByText(/No meetings yet/).waitFor({ timeout: 10000 });
  await shot(sam, '05-stranger-empty-list');
  check('STR-01', 'An uninvited person sees nothing and gets 403', mine.length === 0 && direct.status() === 403, `list size ${mine.length}; opening it directly -> ${direct.status()}`);
});

await guard('ORG-01', 'The organizer keeps full access', async () => {
  const oliveTok = await token(olive);
  const list = await (await call(olive, 'GET', '/meetings', oliveTok)).json();
  const id = list.find((m) => m.title === 'Budget review').id;
  const minutes = await (await call(olive, 'GET', `/meetings/${id}/minutes`, oliveTok)).json();
  const save = await call(olive, 'PUT', `/meetings/${id}/minutes`, oliveTok, { content: minutes });
  check('ORG-01', 'The organizer keeps full access', save.status() === 200 && list.find((m) => m.title === 'Budget review').owned === true, `save -> ${save.status()}`);
});

await guard('ADM-01', 'The administrator sees every meeting', async () => {
  await admin.getByRole('button', { name: 'All meetings' }).click();
  const table = await admin.getByRole('table', { name: 'Meetings' }).innerText();
  await shot(admin, '06-admin-all-meetings');
  check('ADM-01', 'The administrator sees every meeting', /Budget review/.test(table) && /olive@example\.com/.test(table));
});

await fs.writeFile(path.join(OUT, 'results.json'), JSON.stringify(results, null, 2));
await browser.close();
const failed = results.filter((r) => !r.pass).length;
console.log(`\n${results.length - failed}/${results.length} checks passed. Details: docs/roles-validation/results.json`);
process.exit(failed ? 1 : 0);
