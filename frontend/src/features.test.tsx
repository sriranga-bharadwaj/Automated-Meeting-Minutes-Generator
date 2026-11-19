// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom/vitest';
import ActionTracker from './components/ActionTracker';
import AdminConsole from './components/AdminConsole';
import ShareMinutes from './components/ShareMinutes';
import TranscriptPanel from './components/TranscriptPanel';
import VersionHistory from './components/VersionHistory';
import { ApiError, api, secondsLeft } from './api';
import { formatTime } from './utils';
import type { User } from './types';

vi.mock('./api', async (original) => ({
  ...await original<typeof import('./api')>(),
  api: {
    listActions: vi.fn(), setActionStatus: vi.fn(), shareMinutes: vi.fn(), listVersions: vi.fn(), restoreVersion: vi.fn(),
    getTranscript: vi.fn(), saveTranscript: vi.fn(), audioUrl: vi.fn(), adminJobs: vi.fn(), listUsers: vi.fn(),
    adminAudit: vi.fn(), verifyAudit: vi.fn(), changeRole: vi.fn(), runRetention: vi.fn(), runReminders: vi.fn(),
  },
}));

const admin: User = { id: 'u1', name: 'Admin', email: 'admin@example.com', role: 'admin' };
const ravi: User = { id: 'u2', name: 'Ravi', email: 'ravi@example.com', role: 'organizer' };

beforeEach(() => {
  vi.clearAllMocks();
  URL.revokeObjectURL = vi.fn();   // jsdom has no blob URLs; the transcript panel frees its audio URL
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

const rows = [
  { meeting_id: 'm1', meeting_title: 'Weekly', id: 'a1', task: 'Arrange the server', owner: 'Karthik', due: '2026-11-10', status: 'Open' as const, overdue: true, can_edit: true },
  { meeting_id: 'm1', meeting_title: 'Weekly', id: 'a2', task: 'Update the test document', owner: 'Asha', due: '', status: 'Done' as const, overdue: false, can_edit: true },
];

describe('ActionTracker', () => {
  it('lists actions, flags overdue ones and marks one done', async () => {
    vi.mocked(api.listActions).mockResolvedValue(rows);
    vi.mocked(api.setActionStatus).mockResolvedValue();
    render(<ActionTracker onOpenMeeting={vi.fn()} />);
    expect(await screen.findByText('Arrange the server')).toBeVisible();
    expect(screen.getByText('overdue')).toBeVisible();
    await userEvent.click(screen.getByRole('checkbox', { name: 'Mark "Arrange the server" done' }));
    await waitFor(() => expect(api.setActionStatus).toHaveBeenCalledWith('m1', 'a1', 'Done'));
    expect(screen.getByRole('checkbox', { name: 'Mark "Update the test document" done' })).toBeChecked();
  });

  it('sends the filters to the server and opens a meeting', async () => {
    vi.mocked(api.listActions).mockResolvedValue(rows);
    const open = vi.fn();
    render(<ActionTracker onOpenMeeting={open} />);
    await screen.findByText('Arrange the server');
    await userEvent.selectOptions(screen.getByLabelText('Status filter'), 'Open');
    await waitFor(() => expect(api.listActions).toHaveBeenLastCalledWith({ status: 'Open', owner: '', overdue: false }));
    await userEvent.click(screen.getByLabelText('Overdue only'));
    await waitFor(() => expect(api.listActions).toHaveBeenLastCalledWith({ status: 'Open', owner: '', overdue: true }));
    await userEvent.click(screen.getAllByRole('button', { name: 'Weekly' })[0]);
    expect(open).toHaveBeenCalledWith('m1', true);
  });

  it('shows an empty state', async () => {
    vi.mocked(api.listActions).mockResolvedValue([]);
    render(<ActionTracker onOpenMeeting={vi.fn()} />);
    expect(await screen.findByText('No action items match.')).toBeVisible();
  });
});

describe('ShareMinutes', () => {
  it('rejects a bad address before sending', async () => {
    render(<ShareMinutes meetingId="m1" suggestions={[]} />);
    await userEvent.type(screen.getByLabelText('Email addresses'), 'Aasha35gmail.com');
    await userEvent.click(screen.getByRole('button', { name: 'Send' }));
    expect(screen.getByRole('alert')).toHaveTextContent('valid email addresses');
    expect(api.shareMinutes).not.toHaveBeenCalled();
  });

  it('sends to every address in the chosen format', async () => {
    vi.mocked(api.shareMinutes).mockResolvedValue({ sent: 2 });
    render(<ShareMinutes meetingId="m1" suggestions={['a@x.com']} />);
    const box = screen.getByLabelText('Email addresses');
    expect(box).toHaveValue('a@x.com');
    await userEvent.clear(box);
    await userEvent.type(box, 'one@x.com, two@x.com');
    await userEvent.selectOptions(screen.getByLabelText('Attachment format'), 'docx');
    await userEvent.click(screen.getByRole('button', { name: 'Send' }));
    expect(await screen.findByRole('status')).toHaveTextContent('Sent to 2 addresses.');
    expect(api.shareMinutes).toHaveBeenCalledWith('m1', ['one@x.com', 'two@x.com'], 'docx');
  });

  it('shows the server problem when the mail cannot be sent', async () => {
    vi.mocked(api.shareMinutes).mockRejectedValue(new ApiError('MAIL_FAILED', 'The mail server could not be reached.', 502));
    render(<ShareMinutes meetingId="m1" suggestions={['a@x.com']} />);
    await userEvent.click(screen.getByRole('button', { name: 'Send' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('could not be reached');
  });
});

describe('VersionHistory', () => {
  const versions = [
    { version: 3, saved_at: null, saved_by: null, current: true },
    { version: 2, saved_at: '2026-11-19T10:00:00', saved_by: 'ravi@example.com', current: false },
    { version: 1, saved_at: '2026-11-19T09:00:00', saved_by: null, current: false },
  ];

  it('explains when there is only one version', async () => {
    vi.mocked(api.listVersions).mockResolvedValue([versions[0]]);
    render(<VersionHistory meetingId="m1" refreshKey={0} onRestored={vi.fn()} />);
    expect(await screen.findByText(/Only one version so far/)).toBeVisible();
  });

  it('restores an older version after confirming', async () => {
    vi.mocked(api.listVersions).mockResolvedValue(versions);
    vi.mocked(api.restoreVersion).mockResolvedValue({ version: 4 });
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    const restored = vi.fn();
    render(<VersionHistory meetingId="m1" refreshKey={0} onRestored={restored} />);
    expect(await screen.findByText('current')).toBeVisible();
    expect(screen.queryByRole('button', { name: 'Restore version 3' })).toBeNull();
    await userEvent.click(screen.getByRole('button', { name: 'Restore version 2' }));
    await waitFor(() => expect(restored).toHaveBeenCalled());
    expect(api.restoreVersion).toHaveBeenCalledWith('m1', 2);
  });

  it('does nothing when the person cancels', async () => {
    vi.mocked(api.listVersions).mockResolvedValue(versions);
    vi.spyOn(window, 'confirm').mockReturnValue(false);
    render(<VersionHistory meetingId="m1" refreshKey={0} onRestored={vi.fn()} />);
    await userEvent.click(await screen.findByRole('button', { name: 'Restore version 1' }));
    expect(api.restoreVersion).not.toHaveBeenCalled();
  });
});

describe('TranscriptPanel', () => {
  const segments = [
    { start: 0, end: 5, text: 'Good morning everyone.', speaker: '' },
    { start: 5, end: 12, text: 'We decided to use a demo.', speaker: '' },
  ];

  it('shows segments with times, edits text and speaker, and saves them', async () => {
    vi.mocked(api.getTranscript).mockResolvedValue({ language: 'en', text: '', segments });
    vi.mocked(api.audioUrl).mockResolvedValue('blob:audio');
    vi.mocked(api.saveTranscript).mockResolvedValue();
    render(<TranscriptPanel meetingId="m1" speakers={['Ravi', 'Meera']} seek={null} />);
    expect(await screen.findByText('▶ 0:05')).toBeVisible();
    const text = screen.getByLabelText('Text of segment 2');
    await userEvent.clear(text);
    await userEvent.type(text, 'We decided on a recorded demo.');
    await userEvent.type(screen.getByLabelText('Speaker for segment 2'), 'Ravi');
    await userEvent.click(screen.getByRole('button', { name: 'Save transcript' }));
    expect(await screen.findByText('Transcript saved')).toBeVisible();
    expect(api.saveTranscript).toHaveBeenCalledWith('m1', [
      segments[0],
      { start: 5, end: 12, text: 'We decided on a recorded demo.', speaker: 'Ravi' },
    ]);
  });

  it('still shows the transcript when the recording cannot be played', async () => {
    vi.mocked(api.getTranscript).mockResolvedValue({ language: 'en', text: '', segments });
    vi.mocked(api.audioUrl).mockRejectedValue(new ApiError('404', 'No recording.', 404));
    render(<TranscriptPanel meetingId="m1" speakers={[]} seek={null} />);
    expect(await screen.findByLabelText('Text of segment 1')).toHaveValue('Good morning everyone.');
  });

  it('reports a transcript that is not there yet', async () => {
    vi.mocked(api.getTranscript).mockRejectedValue(new ApiError('404', 'There is no transcript yet.', 404));
    vi.mocked(api.audioUrl).mockRejectedValue(new ApiError('404', 'x', 404));
    render(<TranscriptPanel meetingId="m1" speakers={[]} seek={null} />);
    expect(await screen.findByRole('alert')).toHaveTextContent('no transcript yet');
  });
});

describe('AdminConsole', () => {
  beforeEach(() => {
    vi.mocked(api.adminJobs).mockResolvedValue([
      { meeting_id: 'm1', title: 'Weekly', owner_email: 'ravi@example.com', status: 'READY', progress: 100, error: null, audio_file: 'rec.m4a', audio_bytes: 1048576, created_at: null },
      { meeting_id: 'm2', title: 'Broken', owner_email: null, status: 'FAILED', progress: 0, error: 'Could not decode audio file', audio_file: null, audio_bytes: null, created_at: null },
    ]);
    vi.mocked(api.listUsers).mockResolvedValue([admin, ravi]);
    vi.mocked(api.adminAudit).mockResolvedValue([{ id: 1, ts: '2026-11-19T10:00:00', actor: 'admin@example.com', event: 'login', detail: '' }]);
  });

  it('shows jobs with their problem, users and the audit log', async () => {
    render(<AdminConsole me={admin} />);
    const jobs = await screen.findByRole('table', { name: 'Processing jobs' });
    expect(within(jobs).getByText('Could not decode audio file')).toBeVisible();
    expect(within(jobs).getByText('rec.m4a (1.0 MB)')).toBeVisible();
    expect(within(screen.getByRole('table', { name: 'Audit log' })).getByText('login')).toBeVisible();
    expect(screen.getByLabelText('Role of admin@example.com')).toBeDisabled();       // you cannot demote yourself here
  });

  it('changes a role', async () => {
    vi.mocked(api.changeRole).mockResolvedValue({ ...ravi, role: 'admin' });
    render(<AdminConsole me={admin} />);
    await userEvent.selectOptions(await screen.findByLabelText('Role of ravi@example.com'), 'admin');
    await waitFor(() => expect(api.changeRole).toHaveBeenCalledWith('u2', 'admin'));
    expect(await screen.findByRole('status')).toHaveTextContent('ravi@example.com is now admin.');
  });

  it('checks the audit log and reports tampering', async () => {
    vi.mocked(api.verifyAudit).mockResolvedValue({ intact: false, first_bad_id: 7 });
    render(<AdminConsole me={admin} />);
    await userEvent.click(await screen.findByRole('button', { name: 'Check that the log is untouched' }));
    expect(await screen.findByRole('status')).toHaveTextContent('first bad entry is #7');
  });

  it('runs retention only after confirming and validates the number of days', async () => {
    vi.mocked(api.runRetention).mockResolvedValue({ removed: 2, days: 30 });
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
    render(<AdminConsole me={admin} />);
    const days = await screen.findByLabelText('Retention days');
    await userEvent.clear(days);
    await userEvent.type(days, 'abc');
    await userEvent.click(screen.getByRole('button', { name: /Delete meetings older/ }));
    expect(await screen.findByRole('alert')).toHaveTextContent('whole number of days');
    await userEvent.clear(days);
    await userEvent.type(days, '30');
    await userEvent.click(screen.getByRole('button', { name: /Delete meetings older/ }));
    expect(api.runRetention).not.toHaveBeenCalled();                                   // cancelled
    confirm.mockReturnValue(true);
    await userEvent.click(screen.getByRole('button', { name: /Delete meetings older/ }));
    expect(await screen.findByRole('status')).toHaveTextContent('Deleted 2 meeting(s) older than 30 days.');
  });

  it('shows the mail problem when reminders cannot be sent', async () => {
    vi.mocked(api.runReminders).mockRejectedValue(new ApiError('MAIL_FAILED', 'Email is not set up on the server.', 502));
    render(<AdminConsole me={admin} />);
    await userEvent.click(await screen.findByRole('button', { name: 'Send deadline reminders now' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('not set up');
  });
});

describe('helpers', () => {
  it('formatTime shows minutes and seconds', () => {
    expect(formatTime(0)).toBe('0:00');
    expect(formatTime(83.9)).toBe('1:23');
    expect(formatTime(600)).toBe('10:00');
    expect(formatTime(-4)).toBe('0:00');
  });

  it('secondsLeft reads the expiry of a token', () => {
    const make = (exp: number) => `h.${btoa(JSON.stringify({ exp })).replace(/=/g, '')}.s`;
    const soon = Math.floor(Date.now() / 1000) + 30;
    expect(Math.round(secondsLeft(make(soon)))).toBeGreaterThan(25);
    expect(secondsLeft(make(soon))).toBeLessThan(31);
    expect(secondsLeft('garbage')).toBe(0);
  });
});
