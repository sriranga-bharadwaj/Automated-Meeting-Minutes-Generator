import { describe, expect, it } from 'vitest';
import { isLowConfidence, moveItem, toMarkdown, validateAudio, validateMeeting } from './utils';
import type { Minutes } from './types';

describe('validateAudio (TC-FE-02, TC-Aud-01)', () => {
  it('accepts supported formats', () => {
    for (const n of ['a.mp3', 'a.WAV', 'a.m4a', 'a.mp4']) expect(validateAudio({ name: n, size: 1000 })).toBeNull();
  });
  it('rejects unsupported type, empty and oversize files', () => {
    expect(validateAudio({ name: 'notes.txt', size: 10 })).toMatch(/Unsupported/);
    expect(validateAudio({ name: 'a.mp3', size: 0 })).toMatch(/empty/);
    expect(validateAudio({ name: 'a.mp3', size: 600 * 1024 * 1024 })).toMatch(/too large/);
  });
});

describe('validateMeeting (TC-FE-01)', () => {
  const ok = { title: 'T', datetime: '2026-11-02T10:00', agenda: '', language: 'en' as const, attendees: [{ name: 'A', email: 'a@x.com' }] };
  it('passes a valid meeting', () => expect(validateMeeting(ok)).toEqual({}));
  it('flags empty title and missing date', () => {
    const e = validateMeeting({ ...ok, title: ' ', datetime: '' });
    expect(e.title).toBeDefined();
    expect(e.datetime).toBeDefined();
  });
  it('flags invalid attendee email and no attendees', () => {
    expect(validateMeeting({ ...ok, attendees: [{ name: 'A', email: 'nope' }] }).attendees).toBeDefined();
    expect(validateMeeting({ ...ok, attendees: [{ name: '', email: '' }] }).attendees).toBeDefined();
  });
});

describe('confidence (TC-FE-03)', () => {
  it('flags only values below 0.6', () => {
    expect(isLowConfidence(0.59)).toBe(true);
    expect(isLowConfidence(0.6)).toBe(false);
    expect(isLowConfidence(0.95)).toBe(false);
  });
});

describe('moveItem and toMarkdown (TC-Min-02, TC-Min-05)', () => {
  it('reorders and ignores out-of-range moves', () => {
    expect(moveItem([1, 2, 3], 0, 1)).toEqual([2, 1, 3]);
    expect(moveItem([1, 2, 3], 0, -1)).toEqual([1, 2, 3]);
  });
  it('renders all minutes sections', () => {
    const m: Minutes = {
      version: 1, title: 'Sync', datetime: '2026-11-02T10:00', agenda: 'Status', attendees: [{ name: 'Asha', email: 'a@x.com' }],
      topics: [{ id: '1', title: 'Topic', summary: 'Sum' }], decisions: [{ id: '2', statement: 'Do X', confidence: 1 }],
      actionItems: [{ id: '3', task: 'Ship', owner: 'Asha', due: '2026-11-05', status: 'Open', confidence: 1 }],
    };
    const md = toMarkdown(m);
    for (const s of ['# Minutes of Meeting: Sync', '## Key Discussions', '## Decisions', '| Ship | Asha | 2026-11-05 | Open |']) expect(md).toContain(s);
  });
});
