import { test, expect } from '@playwright/test';
import axe from 'axe-core';
test('keyboard, validation, accessibility and mobile layout', async ({ page }) => {
 await page.goto('/');
 await page.keyboard.press('Tab');
 await expect(page.getByLabel('Title', { exact: true })).toBeFocused();
 await page.getByRole('button', { name: /Create meeting/ }).click();
 await expect(page.getByText('Title is required.')).toBeVisible();
 await page.addScriptTag({ content: axe.source });
 const violations = await page.evaluate(async () => (await (window as any).axe.run()).violations.map((v: any) => ({ id: v.id, impact: v.impact })));
 expect(violations).toEqual([]);
 await page.setViewportSize({ width: 375, height: 812 });
 expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
test('meeting creation and invalid audio recovery', async ({ page }) => {
 await page.goto('/');
 await page.getByLabel('Title', { exact: true }).fill('Sprint review');
 await page.getByLabel('Date and time').fill('2026-11-18T10:00');
 await page.getByLabel('Attendee 1 name').fill('Siddhant');
 await page.getByLabel('Attendee 1 email').fill('s@example.com');
 await page.getByRole('button', { name: /Create meeting/ }).click();
 await expect(page.getByRole('heading', { name: /Add the meeting audio/ })).toBeVisible();
 await page.getByLabel('Audio file').setInputFiles({ name: 'notes.txt', mimeType: 'text/plain', buffer: Buffer.from('text') });
 await expect(page.getByRole('alert')).toContainText('Unsupported');
 await expect(page.getByRole('button', { name: /Upload and generate/ })).toBeDisabled();
});
