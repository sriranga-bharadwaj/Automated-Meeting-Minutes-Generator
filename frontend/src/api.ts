import type { ExportFormat, JobStatus, MeetingInput, Minutes } from './types';
import { cleanAttendees, downloadBlob, toMarkdown, uid } from './utils';

export const USE_MOCK = import.meta.env.VITE_USE_MOCK !== 'false';
const BASE: string = import.meta.env.VITE_API_URL ?? '/api/v1';

export class ApiError extends Error {
  constructor(public code: string, message: string, public httpStatus = 0) {
    super(message);
  }
}

const FRIENDLY: Record<number, string> = {
  400: 'Some of the details are invalid. Please check and try again.',
  401: 'Your session has expired. Please log in again.',
  403: 'You do not have access to this meeting.',
  404: 'That meeting could not be found.',
  409: 'Someone else changed these minutes. Reload to see the latest version.',
  413: 'The file is too large. The maximum size is 500 MB.',
  415: 'This file type is not supported. Use MP3, WAV, M4A or MP4.',
  429: 'Too many requests. Please wait a moment and retry.',
  502: 'The mail server could not be reached.',
};

async function toError(res: Response): Promise<ApiError> {
  let body: { code?: string; message?: string } = {};
  try { body = await res.json(); } catch { /* not json */ }
  const msg = res.status >= 500 && res.status !== 502
    ? 'Something went wrong on the server. Please try again.'
    : FRIENDLY[res.status] ?? body.message ?? 'Request failed.';
  return new ApiError(body.code ?? String(res.status), msg, res.status);
}

async function http(path: string, init: RequestInit = {}): Promise<Response> {
  const token = sessionStorage.getItem('ammg_token');
  const headers: Record<string, string> = { ...(init.headers as Record<string, string>) };
  if (token) headers.Authorization = `Bearer ${token}`;
  let res: Response;
  try {
    res = await fetch(BASE + path, { ...init, headers });
  } catch {
    throw new ApiError('NETWORK', 'Cannot reach the server. Check that the backend is running and try again.');
  }
  if (!res.ok) throw await toError(res);
  return res;
}

const json = (body: unknown): RequestInit => ({
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
});

/* ------------------------------ real backend ------------------------------ */

const real = {
  async createMeeting(m: MeetingInput): Promise<{ meetingId: string }> {
    const res = await http('/meetings', { method: 'POST', ...json({ ...m, attendees: cleanAttendees(m.attendees) }) });
    return res.json();
  },
  uploadAudio(id: string, file: Blob, name: string, onProgress: (pct: number) => void): Promise<void> {
    // XMLHttpRequest is used because fetch cannot report upload progress.
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open('POST', `${BASE}/meetings/${id}/audio`);
      const token = sessionStorage.getItem('ammg_token');
      if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`);
      xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(Math.round((e.loaded / e.total) * 100));
      xhr.onerror = () => reject(new ApiError('NETWORK', 'Upload failed. Check your connection and try again.'));
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) return resolve();
        reject(new ApiError(String(xhr.status), FRIENDLY[xhr.status] ?? 'Upload failed.', xhr.status));
      };
      const form = new FormData();
      form.append('file', file, name);
      xhr.send(form);
    });
  },
  async getStatus(id: string): Promise<JobStatus> {
    return (await http(`/meetings/${id}/status`)).json();
  },
  async retry(id: string): Promise<void> {
    await http(`/meetings/${id}/retry`, { method: 'POST' });
  },
  async getMinutes(id: string): Promise<Minutes> {
    const raw = await (await http(`/meetings/${id}/minutes`)).json();
    // Backend items may not carry ids/status yet, so normalise them here.
    return {
      version: raw.version ?? 1,
      title: raw.title ?? '',
      datetime: raw.datetime ?? '',
      agenda: raw.agenda ?? '',
      attendees: raw.attendees ?? [],
      topics: (raw.topics ?? []).map((t: any) => ({ id: t.id ?? uid(), title: t.title ?? '', summary: t.summary ?? '' })),
      decisions: (raw.decisions ?? []).map((d: any) => ({ id: d.id ?? uid(), statement: d.statement ?? d.text ?? '', confidence: d.confidence ?? 1 })),
      actionItems: (raw.actionItems ?? []).map((a: any) => ({
        id: a.id ?? uid(), task: a.task ?? '', owner: a.owner || 'Unassigned', due: a.due ?? '',
        status: a.status === 'Done' ? 'Done' : 'Open', confidence: a.confidence ?? 1,
      })),
    };
  },
  async saveMinutes(id: string, m: Minutes): Promise<{ version: number }> {
    return (await http(`/minutes/${id}`, { method: 'PUT', ...json({ content: m }) })).json();
  },
  async exportMinutes(id: string, m: Minutes, fmt: ExportFormat): Promise<void> {
    const res = await http(`/minutes/${id}/export`, { method: 'POST', ...json({ format: fmt }) });
    downloadBlob(await res.blob(), `minutes.${fmt}`);
  },
};

/* ------------------------------ mock backend ------------------------------ */

interface MockJob { input: MeetingInput; startedAt: number; fail: boolean }
const jobs = new Map<string, MockJob>();
const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

function mockMinutes(job: MockJob): Minutes {
  const names = job.input.attendees.map((a) => a.name).filter(Boolean);
  const a = names[0] ?? 'Unassigned';
  const b = names[1] ?? names[0] ?? 'Unassigned';
  return {
    version: 1,
    title: job.input.title,
    datetime: job.input.datetime,
    agenda: job.input.agenda,
    attendees: job.input.attendees,
    topics: [
      { id: uid(), title: 'Project status', summary: 'Backend endpoints are in place and the team is integrating transcription with the API.' },
      { id: uid(), title: 'Frontend demo plan', summary: 'The UI will show the full upload to minutes workflow, including loading and error states.' },
      { id: uid(), title: 'Testing and reports', summary: 'Unit, system, code coverage and branch coverage reports are due after the sprint.' },
    ],
    decisions: [
      { id: uid(), statement: 'Use FastAPI with a React + TypeScript frontend for the demo.', confidence: 0.92 },
      { id: uid(), statement: 'Run the integration test before the Friday review.', confidence: 0.81 },
    ],
    actionItems: [
      { id: uid(), task: 'Finish the transcription module and share a sample transcript', owner: a, due: '2026-11-04', status: 'Open', confidence: 0.88 },
      { id: uid(), task: 'Connect the minutes UI to the backend API', owner: b, due: '2026-11-05', status: 'Open', confidence: 0.79 },
      { id: uid(), task: 'Somebody should double-check the export formats', owner: 'Unassigned', due: '', status: 'Open', confidence: 0.46 },
    ],
  };
}

const mock = {
  async createMeeting(m: MeetingInput): Promise<{ meetingId: string }> {
    await wait(500);
    const id = uid();
    jobs.set(id, { input: m, startedAt: 0, fail: false });
    return { meetingId: id };
  },
  async uploadAudio(id: string, _file: Blob, name: string, onProgress: (pct: number) => void): Promise<void> {
    const job = jobs.get(id);
    if (!job) throw new ApiError('404', FRIENDLY[404], 404);
    for (let p = 0; p <= 100; p += 10) { onProgress(p); await wait(120); }
    job.startedAt = Date.now();
    job.fail = name.toLowerCase().includes('fail'); // demo: a file named "fail.mp3" triggers the error path
  },
  async getStatus(id: string): Promise<JobStatus> {
    const job = jobs.get(id);
    if (!job) throw new ApiError('404', FRIENDLY[404], 404);
    await wait(150);
    const t = (Date.now() - job.startedAt) / 1000;
    if (job.fail && t > 3) return { status: 'FAILED', progress: 40, error: 'Transcription failed for this recording.' };
    if (t < 1.5) return { status: 'QUEUED', stage: 'Waiting for a worker', progress: 5 };
    if (t < 4) return { status: 'TRANSCRIBING', stage: 'Converting speech to text', progress: 20 + Math.round((t - 1.5) * 12) };
    if (t < 6.5) return { status: 'ANALYSING', stage: 'Finding decisions and action items', progress: 55 + Math.round((t - 4) * 14) };
    return { status: 'READY', stage: 'Minutes ready', progress: 100 };
  },
  async retry(id: string): Promise<void> {
    const job = jobs.get(id);
    if (!job) throw new ApiError('404', FRIENDLY[404], 404);
    job.fail = false;
    job.startedAt = Date.now();
  },
  async getMinutes(id: string): Promise<Minutes> {
    const job = jobs.get(id);
    if (!job) throw new ApiError('404', FRIENDLY[404], 404);
    await wait(400);
    return mockMinutes(job);
  },
  async saveMinutes(_id: string, m: Minutes): Promise<{ version: number }> {
    await wait(300);
    return { version: m.version + 1 };
  },
  async exportMinutes(_id: string, m: Minutes, fmt: ExportFormat): Promise<void> {
    await wait(200);
    const md = toMarkdown(m);
    if (fmt === 'md') return downloadBlob(new Blob([md], { type: 'text/markdown' }), 'minutes.md');
    if (fmt === 'pdf') return window.print();
    const esc = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;');
    const html = `<html><body><pre style="font-family:Calibri,sans-serif;white-space:pre-wrap">${esc(md)}</pre></body></html>`;
    downloadBlob(new Blob([html], { type: 'application/msword' }), 'minutes.doc');
  },
};

export const api = USE_MOCK ? mock : real;
