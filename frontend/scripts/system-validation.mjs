// System validation: drives the real app (real backend) and saves a screenshot per step.
// Usage (backend on :8000, frontend on :5173):  node scripts/system-validation.mjs
// Results go to ../docs/system-validation/ (screenshots, downloads, results.json).
import { chromium } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';

const BASE = process.env.BASE_URL ?? 'http://localhost:5173';
const OUT = path.resolve('../docs/system-validation');
const REC = path.resolve('../eval/recordings');
await fs.mkdir(path.join(OUT, 'downloads'), { recursive: true });

const results = [];   // one entry per test case
const extracted = {}; // minutes JSON per run
const log = (id, name, pass, detail, shot) => {
  results.push({ id, name, pass, detail, shot });
  console.log(`${pass ? 'PASS' : 'FAIL'} ${id} ${name} :: ${detail}`);
};

const browser = await chromium.launch({ channel: 'chrome' });
const context = await browser.newContext({ viewport: { width: 1280, height: 900 }, acceptDownloads: true });

async function shot(page, name) {
  const file = `${name}.png`;
  await page.screenshot({ path: path.join(OUT, file), fullPage: true });
  return `system-validation/${file}`;
}

// Runs one full meeting flow with one audio file. `tag` prefixes IDs and file names.
async function runFlow(tag, audioPath, { edit, exports }) {
  const page = await context.newPage();
  let meetingId = '';
  page.on('response', async (r) => {
    if (r.request().method() === 'POST' && /\/api\/v1\/meetings$/.test(r.url()) && r.ok()) {
      try { const j = await r.json(); meetingId = j.id ?? j.meetingId ?? meetingId; } catch { /* ignore */ }
    }
  });
  await page.goto(BASE);

  // 1. create meeting
  try {
    await page.getByLabel('Title', { exact: true }).fill(`Sprint review (${tag})`);
    await page.getByLabel('Date and time').fill('2026-11-18T10:00');
    await page.getByLabel('Agenda').fill('Demo, testing, documents');
    const people = [['Ravi', 'ravi@example.com'], ['Meera', 'meera@example.com'], ['Asha', 'asha@example.com']];
    for (let i = 0; i < people.length; i++) {
      if (i > 0) await page.getByRole('button', { name: '+ Add attendee' }).click();
      await page.getByLabel(`Attendee ${i + 1} name`).fill(people[i][0]);
      await page.getByLabel(`Attendee ${i + 1} email`).fill(people[i][1]);
    }
    const s1 = await shot(page, `${tag}-01-meeting-form`);
    await page.getByRole('button', { name: /Create meeting/ }).click();
    await page.getByRole('heading', { name: /Add the meeting audio/ }).waitFor({ timeout: 15000 });
    const s2 = await shot(page, `${tag}-02-audio-step`);
    log(`${tag}-TC01`, 'Create meeting with attendees Ravi, Meera, Asha', true, `meeting id ${meetingId}`, s2);
  } catch (e) {
    log(`${tag}-TC01`, 'Create meeting with attendees Ravi, Meera, Asha', false, String(e.message).split('\n')[0], await shot(page, `${tag}-01-failed`));
    await page.close();
    return;
  }

  // 2. upload + processing
  const t0 = Date.now();
  try {
    await page.getByLabel('Audio file').setInputFiles(audioPath);
    await page.getByRole('button', { name: /Upload and generate/ }).click();
    await page.getByRole('heading', { name: 'Generating your minutes' }).waitFor({ timeout: 30000 });
    await page.waitForTimeout(1500);
    const sp = await shot(page, `${tag}-03-progress`);
    log(`${tag}-TC02`, `Upload ${path.basename(audioPath)} and show progress screen`, true, 'progress screen shown', sp);
    await page.getByLabel('Topic title').first().waitFor({ timeout: 600000 });
    const secs = ((Date.now() - t0) / 1000).toFixed(0);
    const sm = await shot(page, `${tag}-04-minutes`);
    log(`${tag}-TC03`, 'Processing completes and minutes are shown', true, `ready after ${secs}s`, sm);
  } catch (e) {
    log(`${tag}-TC03`, 'Processing completes and minutes are shown', false, String(e.message).split('\n')[0], await shot(page, `${tag}-03-failed`));
    await page.close();
    return;
  }

  // capture the generated minutes straight from the backend for the comparison step
  try {
    const res = await page.request.get(`${BASE}/api/v1/meetings/${meetingId}/minutes`);
    extracted[tag] = await res.json();
  } catch { /* reported later */ }

  // 3. edit + autosave
  if (edit) {
    try {
      const field = page.getByLabel('Topic title').first();
      await field.fill('Demo format (edited by validation)');
      await page.getByText('All changes saved').waitFor({ timeout: 15000 });
      log(`${tag}-TC04`, 'Edit a field and see "All changes saved"', true, 'saved indicator shown', await shot(page, `${tag}-05-saved`));
    } catch (e) {
      log(`${tag}-TC04`, 'Edit a field and see "All changes saved"', false, String(e.message).split('\n')[0], await shot(page, `${tag}-05-failed`));
    }
  }

  // 4. exports
  if (exports) {
    for (const [label, ext, n] of [['Word (DOCX)', 'docx', '06'], ['PDF', 'pdf', '07'], ['Markdown', 'md', '08']]) {
      try {
        const dl = page.waitForEvent('download', { timeout: 30000 });
        await page.getByRole('button', { name: label, exact: true }).click();
        const d = await dl;
        const dest = path.join(OUT, 'downloads', `${tag}-minutes.${ext}`);
        await d.saveAs(dest);
        const size = (await fs.stat(dest)).size;
        log(`${tag}-TC${n}`, `Export ${label}`, size > 0, `${d.suggestedFilename()} (${size} bytes)`, await shot(page, `${tag}-${n}-export-${ext}`));
      } catch (e) {
        log(`${tag}-TC${n}`, `Export ${label}`, false, String(e.message).split('\n')[0], await shot(page, `${tag}-${n}-export-${ext}-failed`));
      }
    }
  }
  await page.close();
}

// Corrupt file: a text file renamed to .mp3
async function runCorrupt() {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'ammg-corrupt-'));
  const bad = path.join(dir, 'corrupt.mp3');
  await fs.writeFile(bad, 'this is plain text, not audio');
  const page = await context.newPage();
  await page.goto(BASE);
  try {
    await page.getByLabel('Title', { exact: true }).fill('Corrupt upload test');
    await page.getByLabel('Date and time').fill('2026-11-18T11:00');
    await page.getByLabel('Attendee 1 name').fill('Ravi');
    await page.getByLabel('Attendee 1 email').fill('ravi@example.com');
    await page.getByRole('button', { name: /Create meeting/ }).click();
    await page.getByRole('heading', { name: /Add the meeting audio/ }).waitFor({ timeout: 15000 });
    await page.getByLabel('Audio file').setInputFiles(bad);
    await page.getByRole('button', { name: /Upload and generate/ }).click();
    const failed = page.getByRole('heading', { name: 'Processing failed' });
    const alert = page.getByRole('alert');
    await Promise.race([failed.waitFor({ timeout: 120000 }), alert.waitFor({ timeout: 120000 })]);
    const retryVisible = await page.getByRole('button', { name: 'Retry', exact: true }).isVisible().catch(() => false);
    const msg = (await page.locator('main, body').first().innerText()).split('\n').filter((l) => /fail|error|could not|unsupported|decode/i.test(l)).slice(0, 3).join(' | ');
    log('CORRUPT-TC01', 'Corrupt .mp3 shows an error and a Retry button', retryVisible, `message: ${msg || '(none found)'}; Retry visible: ${retryVisible}`, await shot(page, 'corrupt-01-error'));
  } catch (e) {
    log('CORRUPT-TC01', 'Corrupt .mp3 shows an error and a Retry button', false, String(e.message).split('\n')[0], await shot(page, 'corrupt-01-failed'));
  }
  await page.close();
}

await runFlow('quiet', path.join(REC, 'quiet_room.wav'), { edit: true, exports: true });
await runCorrupt();
await runFlow('two', path.join(REC, 'two_speakers.wav'), { edit: false, exports: false });

await fs.writeFile(path.join(OUT, 'results.json'), JSON.stringify({ results, extracted }, null, 2));
await browser.close();
const failed = results.filter((r) => !r.pass).length;
console.log(`\n${results.length - failed}/${results.length} cases passed. Details: docs/system-validation/results.json`);
