// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom/vitest';
import ActionTracker from './components/ActionTracker';
import MeetingList from './components/MeetingList';
import MinutesEditor from './components/MinutesEditor';
import { api } from './api';
import type { Minutes, User } from './types';

// AMG-F-002: Admin, Organizer and Participant; invited people can only view.
vi.mock('./api', async (original) => ({
  ...await original<typeof import('./api')>(),
  api: {
    listMeetings: vi.fn(), listUsers: vi.fn(), deleteMeeting: vi.fn(), listActions: vi.fn(), setActionStatus: vi.fn(),
    getMinutes: vi.fn(), saveMinutes: vi.fn(), exportMinutes: vi.fn(), getTranscript: vi.fn(), audioUrl: vi.fn(),
    listVersions: vi.fn(), restoreVersion: vi.fn(), shareMinutes: vi.fn(),
  },
}));

const organizer: User = { id: 'u1', name: 'Olive', email: 'olive@example.com', role: 'organizer' };
const participant: User = { id: 'u2', name: 'Pat', email: 'pat@example.com', role: 'participant' };

beforeEach(() => {
  vi.clearAllMocks();
  URL.revokeObjectURL = vi.fn();
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

const meetings = [
  { id: 'm1', title: 'My own meeting', status: 'processed', created_at: '2026-11-19T10:00:00Z', owner_email: 'olive@example.com', owned: true },
  { id: 'm2', title: 'Budget review', status: 'processed', created_at: '2026-11-18T10:00:00Z', owner_email: 'boss@example.com', owned: false },
];

describe('meeting list by role', () => {
  it('an organizer can create meetings, delete their own, and only view invited ones', async () => {
    vi.mocked(api.listMeetings).mockResolvedValue(meetings);
    const open = vi.fn();
    render(<MeetingList user={organizer} onNew={vi.fn()} onOpen={open} />);
    expect(await screen.findByRole('heading', { name: 'My meetings' })).toBeVisible();
    expect(screen.getByRole('button', { name: '+ New meeting' })).toBeVisible();
    const table = screen.getByRole('table', { name: 'Meetings' });
    expect(within(table).getByText('Owner')).toBeVisible();
    expect(within(table).getByText(/Invited/)).toBeVisible();
    expect(within(table).getByText(/by boss@example.com/)).toBeVisible();
    expect(screen.getByRole('button', { name: 'Delete My own meeting' })).toBeVisible();
    expect(screen.queryByRole('button', { name: 'Delete Budget review' })).toBeNull();     // not theirs to delete
    await userEvent.click(screen.getByRole('button', { name: 'Open Budget review' }));
    expect(open).toHaveBeenCalledWith(meetings[1]);
    expect(screen.getByRole('button', { name: 'Open Budget review' })).toHaveTextContent('View');
  });

  it('a participant has no New meeting button and sees only shared meetings', async () => {
    vi.mocked(api.listMeetings).mockResolvedValue([meetings[1]]);
    render(<MeetingList user={participant} onNew={vi.fn()} onOpen={vi.fn()} />);
    expect(await screen.findByRole('heading', { name: 'Meetings shared with me' })).toBeVisible();
    expect(screen.queryByRole('button', { name: '+ New meeting' })).toBeNull();
    expect(screen.queryByRole('button', { name: /Delete/ })).toBeNull();
    expect(screen.getByText('Budget review')).toBeVisible();
  });

  it('a participant with nothing shared is told how meetings appear', async () => {
    vi.mocked(api.listMeetings).mockResolvedValue([]);
    render(<MeetingList user={participant} onNew={vi.fn()} onOpen={vi.fn()} />);
    expect(await screen.findByText(/adds your email address as an attendee/)).toBeVisible();
  });
});

describe('action tracker', () => {
  it('the Done checkbox is disabled for meetings the person was only invited to', async () => {
    vi.mocked(api.listActions).mockResolvedValue([
      { meeting_id: 'm1', meeting_title: 'Mine', id: 'a1', task: 'Own task', owner: 'Olive', due: '', status: 'Open', overdue: false, can_edit: true },
      { meeting_id: 'm2', meeting_title: 'Shared', id: 'a2', task: 'Shared task', owner: 'Boss', due: '', status: 'Open', overdue: false, can_edit: false },
    ]);
    const open = vi.fn();
    render(<ActionTracker onOpenMeeting={open} />);
    expect(await screen.findByRole('checkbox', { name: 'Mark "Own task" done' })).toBeEnabled();
    expect(screen.getByRole('checkbox', { name: 'Mark "Shared task" done' })).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: 'Shared' }));
    expect(open).toHaveBeenCalledWith('m2', false);
  });
});

describe('minutes of an invited meeting', () => {
  const minutes: Minutes = {
    version: 1, title: 'Budget review', datetime: '2026-11-18T10:00', agenda: '',
    attendees: [{ name: 'Pat', email: 'pat@example.com' }],
    topics: [{ id: 't1', title: 'Budget', summary: 'Costs.', source: { start: 4, end: 9, text: 'Costs are too high.' } }],
    decisions: [{ id: 'd1', statement: 'Cut costs', confidence: 1, source: { start: 9, end: 12, text: 'We cut costs.' } }],
    actionItems: [{ id: 'a1', task: 'Send report', owner: 'Pat', due: '', status: 'Open', confidence: 1, source: { start: 12, end: 15, text: 'Pat sends the report.' } }],
  };

  beforeEach(() => {
    vi.mocked(api.getMinutes).mockResolvedValue(minutes);
    vi.mocked(api.getTranscript).mockResolvedValue({ language: 'en', text: '', segments: [{ start: 0, end: 4, text: 'Hello.', speaker: '' }] });
    vi.mocked(api.audioUrl).mockResolvedValue('blob:x');
    vi.mocked(api.listVersions).mockResolvedValue([
      { version: 2, saved_at: null, saved_by: null, current: true },
      { version: 1, saved_at: '2026-11-18T09:00:00', saved_by: null, current: false },
    ]);
  });

  it('is read only: editing is disabled and sharing, restoring and saving are not offered', async () => {
    render(<MinutesEditor meetingId="m2" readOnly />);
    expect(await screen.findByRole('status')).toHaveTextContent('You were invited to this meeting');
    expect(screen.getByLabelText('Topic title')).toHaveAttribute('readonly');
    expect(screen.getByLabelText('Decision')).toHaveAttribute('readonly');
    expect(screen.getByLabelText('Task')).toHaveAttribute('readonly');
    expect(screen.getByLabelText('Owner')).toBeDisabled();
    expect(screen.getByLabelText('Status')).toBeDisabled();
    for (const name of ['+ Add topic', '+ Add decision', '+ Add action item', 'Delete topic', 'Delete decision', 'Delete action item']) {
      expect(screen.getByRole('button', { name })).toBeDisabled();
    }
    // listening is allowed: the play buttons next to each item stay usable
    for (const button of screen.queryAllByRole('button', { name: /Play recording from/ })) expect(button).toBeEnabled();
    expect(screen.queryByRole('region', { name: 'Share by email' })).toBeNull();
    expect(await screen.findByLabelText('Text of segment 1')).toHaveAttribute('readonly');
    expect(screen.queryByRole('button', { name: 'Save transcript' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Restore version 1' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Start a new meeting' })).toBeNull();   // no onNew given
    // export is allowed
    expect(screen.getByRole('button', { name: 'Markdown' })).toBeEnabled();
    await userEvent.click(screen.getByRole('button', { name: 'Markdown' }));
    expect(api.exportMinutes).toHaveBeenCalled();
  });

  it('the owner still edits, shares and restores', async () => {
    render(<MinutesEditor meetingId="m1" onNew={vi.fn()} />);
    expect(await screen.findByLabelText('Topic title')).not.toHaveAttribute('readonly');
    expect(screen.getByRole('button', { name: '+ Add topic' })).toBeEnabled();
    expect(screen.getByRole('region', { name: 'Share by email' })).toBeVisible();
    expect(await screen.findByRole('button', { name: 'Restore version 1' })).toBeVisible();
    expect(screen.getByRole('button', { name: 'Start a new meeting' })).toBeVisible();
  });
});
