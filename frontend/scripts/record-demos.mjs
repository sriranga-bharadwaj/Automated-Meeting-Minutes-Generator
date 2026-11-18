import { chromium } from '@playwright/test';
import fs from 'node:fs/promises';
const browser = await chromium.launch({ channel: 'chrome' });
await fs.mkdir('../docs/demos', { recursive: true });
for (const [sprint, duration] of [[1, 60000], [2, 120000]]) {
 const context = await browser.newContext({ viewport: { width: 1280, height: 800 }, recordVideo: { dir: '../docs/demos', size: { width: 1280, height: 800 } } });
 const page = await context.newPage();
 await page.goto('http://127.0.0.1:5181');
 const start = Date.now();
 async function caption(text) { await page.evaluate(text => { let el = document.getElementById('demo-caption'); if (!el) { el = document.createElement('div'); el.id = 'demo-caption'; el.style.cssText = 'position:fixed;bottom:0;left:0;right:0;padding:16px;background:#102238;color:white;z-index:9999;font:18px sans-serif;text-align:center'; document.body.append(el); } el.textContent = text; }, text); }
 await caption(`Sprint ${sprint} frontend demonstration — offline mock API`);
 await page.waitForTimeout(5000);
 await page.getByRole('button', { name: /Create meeting/ }).click();
 await caption('Required-field validation prevents incomplete meetings');
 await page.waitForTimeout(5000);
 for (const [label, value] of [['Title', `Sprint ${sprint} review`], ['Date and time', '2026-11-18T10:00'], ['Attendee 1 name', 'Siddhant'], ['Attendee 1 email', 'siddhant@example.com'], ['Agenda', 'Review progress, decisions and next steps']]) { await page.getByLabel(label, { exact: true }).fill(value); await page.waitForTimeout(1000); }
 await page.getByRole('button', { name: /Create meeting/ }).click();
 await page.getByRole('heading', { name: /Add the meeting audio/ }).waitFor();
 await caption('Create a meeting, then upload audio or record in the browser');
 await page.waitForTimeout(5000);
 await page.getByLabel('Audio file').setInputFiles({ name: 'notes.txt', mimeType: 'text/plain', buffer: Buffer.from('unsupported') });
 await caption('Unsupported files are rejected with a recovery message');
 await page.waitForTimeout(5000);
 await page.getByLabel('Audio file').setInputFiles({ name: 'sample.wav', mimeType: 'audio/wav', buffer: Buffer.from('mock-only fixture; no transcription performed') });
 if (sprint === 2) {
  await page.getByRole('button', { name: /Upload and generate/ }).click();
  await caption('Mock processing demonstrates progress through transcription and analysis');
  await page.getByRole('heading', { name: 'Sprint 2 review' }).waitFor();
  await caption('Review generated sample discussions, decisions and action items');
  await page.waitForTimeout(7000);
  await page.getByLabel('Topic title').first().fill('Frontend coverage and accessibility');
  await caption('Edit discussions; changes are saved by the demo API');
  await page.waitForTimeout(7000);
  await page.getByRole('button', { name: '+ Add decision', exact: true }).click();
  await page.getByLabel('Decision', { exact: true }).last().fill('Run UI and browser checks before release');
  await page.getByLabel('Decision', { exact: true }).last().scrollIntoViewIfNeeded();
  await page.waitForTimeout(7000);
  await page.getByRole('button', { name: 'Markdown', exact: true }).scrollIntoViewIfNeeded();
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Markdown', exact: true }).click();
  await download;
  await caption('Export the edited minutes as Markdown; PDF and Word controls are also available');
 }
 await caption(`Sprint ${sprint}: ${sprint === 1 ? 'meeting form, validation and upload selection' : 'upload, progress, editable minutes and Markdown export'} — mock API demonstration`);
 await page.waitForTimeout(Math.max(0, duration - (Date.now() - start)));
 const video = page.video(); await context.close(); await video.saveAs(`../docs/demos/sprint-${sprint}.webm`); await fs.unlink(await video.path());
}
await browser.close();
