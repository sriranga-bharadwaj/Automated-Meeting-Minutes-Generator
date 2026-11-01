import type { Attendee, MeetingInput, Minutes } from './types';

export const ALLOWED_EXT = ['mp3', 'wav', 'm4a', 'mp4'];
export const MAX_BYTES = 500 * 1024 * 1024;
export const LOW_CONFIDENCE = 0.6;

export const isLowConfidence = (c: number) => c < LOW_CONFIDENCE;
export const uid = () => Math.random().toString(36).slice(2, 10);

export function validateAudio(f: { name: string; size: number }): string | null {
  const ext = f.name.split('.').pop()?.toLowerCase() ?? '';
  if (!ALLOWED_EXT.includes(ext)) return 'Unsupported file type. Use MP3, WAV, M4A or MP4.';
  if (f.size === 0) return 'This file is empty.';
  if (f.size > MAX_BYTES) return 'File is too large. The maximum size is 500 MB.';
  return null;
}

export type MeetingErrors = Partial<Record<'title' | 'datetime' | 'attendees', string>>;
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function validateMeeting(m: MeetingInput): MeetingErrors {
  const e: MeetingErrors = {};
  if (!m.title.trim()) e.title = 'Title is required.';
  if (!m.datetime) e.datetime = 'Date and time are required.';
  const filled = m.attendees.filter((a) => a.name.trim() || a.email.trim());
  if (filled.length === 0) e.attendees = 'Add at least one attendee.';
  else if (filled.some((a) => !a.name.trim() || !EMAIL.test(a.email.trim())))
    e.attendees = 'Every attendee needs a name and a valid email.';
  return e;
}

export const cleanAttendees = (list: Attendee[]) =>
  list.filter((a) => a.name.trim() && a.email.trim()).map((a) => ({ name: a.name.trim(), email: a.email.trim() }));

export function toMarkdown(m: Minutes): string {
  const L: string[] = [`# Minutes of Meeting: ${m.title}`, '', `**Date:** ${m.datetime.replace('T', ' ')}`];
  L.push(`**Attendees:** ${m.attendees.map((a) => a.name).join(', ') || '-'}`, '');
  if (m.agenda.trim()) L.push('## Agenda', m.agenda.trim(), '');
  L.push('## Key Discussions');
  m.topics.forEach((t, i) => L.push(`${i + 1}. **${t.title}**: ${t.summary}`));
  L.push('', '## Decisions');
  m.decisions.forEach((d, i) => L.push(`${i + 1}. ${d.statement}`));
  L.push('', '## Action Items', '| Task | Owner | Deadline | Status |', '| --- | --- | --- | --- |');
  m.actionItems.forEach((a) => L.push(`| ${a.task} | ${a.owner} | ${a.due || '-'} | ${a.status} |`));
  return L.join('\n') + '\n';
}

export function moveItem<T>(list: T[], index: number, dir: -1 | 1): T[] {
  const j = index + dir;
  if (j < 0 || j >= list.length) return list;
  const copy = [...list];
  [copy[index], copy[j]] = [copy[j], copy[index]];
  return copy;
}

export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
