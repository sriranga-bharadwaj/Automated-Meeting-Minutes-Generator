// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi, beforeEach } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom/vitest';
import Login from './components/Login';
import MeetingList from './components/MeetingList';
import { ApiError, api, auth } from './api';
import { friendlyProcessingError, isEmail } from './utils';
import type { User } from './types';

vi.mock('./api', async (original) => ({
  ...await original<typeof import('./api')>(),
  auth: { login: vi.fn(), register: vi.fn(), logout: vi.fn() },
  api: { listMeetings: vi.fn(), listUsers: vi.fn(), deleteMeeting: vi.fn() },
}));

const alice: User = { id: 'u1', name: 'Alice', email: 'alice@example.com', role: 'organizer' };
const admin: User = { id: 'u2', name: 'Admin', email: 'admin@example.com', role: 'admin' };

beforeEach(() => { vi.clearAllMocks(); });
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe('Login', () => {
  it('asks for a valid email before calling the server', async () => {
    render(<Login onLoggedIn={vi.fn()} />);
    await userEvent.type(screen.getByLabelText('Email'), 'Aasha35gmail.com');
    await userEvent.type(screen.getByLabelText('Password'), 'password123');
    await userEvent.click(screen.getByRole('button', { name: 'Log in' }));
    expect(screen.getByText(/Enter a valid email address/)).toBeVisible();
    expect(auth.login).not.toHaveBeenCalled();
  });

  it('logs in and passes the user on', async () => {
    vi.mocked(auth.login).mockResolvedValue(alice);
    const done = vi.fn();
    render(<Login onLoggedIn={done} />);
    await userEvent.type(screen.getByLabelText('Email'), 'alice@example.com');
    await userEvent.type(screen.getByLabelText('Password'), 'password123');
    await userEvent.click(screen.getByRole('button', { name: 'Log in' }));
    await waitFor(() => expect(done).toHaveBeenCalledWith(alice));
    expect(auth.login).toHaveBeenCalledWith('alice@example.com', 'password123');
  });

  it('shows the server message for a wrong password', async () => {
    vi.mocked(auth.login).mockRejectedValue(new ApiError('BAD_CREDENTIALS', 'Email or password is wrong.', 401));
    render(<Login onLoggedIn={vi.fn()} />);
    await userEvent.type(screen.getByLabelText('Email'), 'alice@example.com');
    await userEvent.type(screen.getByLabelText('Password'), 'wrong-pass');
    await userEvent.click(screen.getByRole('button', { name: 'Log in' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Email or password is wrong.');
  });

  it('registration needs a name and an 8 character password', async () => {
    render(<Login onLoggedIn={vi.fn()} />);
    await userEvent.click(screen.getByRole('button', { name: 'Create an account' }));
    await userEvent.type(screen.getByLabelText('Email'), 'new@example.com');
    await userEvent.type(screen.getByLabelText('Password'), 'short');
    await userEvent.click(screen.getByRole('button', { name: 'Create account' }));
    expect(screen.getByText('Name is required.')).toBeVisible();
    expect(screen.getByText('Use at least 8 characters.')).toBeVisible();
    expect(auth.register).not.toHaveBeenCalled();
  });
});

describe('MeetingList', () => {
  const meetings = [
    { id: 'm1', title: 'Weekly project meeting', status: 'processed', created_at: '2026-11-19T10:00:00Z', owner_email: 'alice@example.com' },
    { id: 'm2', title: 'Budget', status: 'created', created_at: '2026-11-18T10:00:00Z', owner_email: 'bob@example.com' },
  ];

  it('lists meetings with a plain status and opens one', async () => {
    vi.mocked(api.listMeetings).mockResolvedValue(meetings);
    const open = vi.fn();
    render(<MeetingList user={alice} onNew={vi.fn()} onOpen={open} />);
    expect(await screen.findByText('Weekly project meeting')).toBeVisible();
    expect(screen.getByText('Minutes ready')).toBeVisible();
    expect(screen.getByText('Waiting for audio')).toBeVisible();
    expect(screen.queryByRole('columnheader', { name: 'Owner' })).toBeNull();   // users do not see owners
    await userEvent.click(screen.getByRole('button', { name: 'Open Budget' }));
    expect(open).toHaveBeenCalledWith(meetings[1]);
  });

  it('administrators also see owners and the user list', async () => {
    vi.mocked(api.listMeetings).mockResolvedValue(meetings);
    vi.mocked(api.listUsers).mockResolvedValue([admin, alice]);
    render(<MeetingList user={admin} onNew={vi.fn()} onOpen={vi.fn()} />);
    expect(await screen.findByRole('columnheader', { name: 'Owner' })).toBeVisible();
    expect(screen.getByText('bob@example.com')).toBeVisible();
    expect(await screen.findByRole('table', { name: 'Users' })).toBeVisible();
  });

  it('deletes after confirming', async () => {
    vi.mocked(api.listMeetings).mockResolvedValue(meetings);
    vi.mocked(api.deleteMeeting).mockResolvedValue();
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    render(<MeetingList user={alice} onNew={vi.fn()} onOpen={vi.fn()} />);
    await userEvent.click(await screen.findByRole('button', { name: 'Delete Budget' }));
    await waitFor(() => expect(screen.queryByText('Budget')).toBeNull());
    expect(api.deleteMeeting).toHaveBeenCalledWith('m2');
  });

  it('does not delete when the person cancels', async () => {
    vi.mocked(api.listMeetings).mockResolvedValue(meetings);
    vi.spyOn(window, 'confirm').mockReturnValue(false);
    render(<MeetingList user={alice} onNew={vi.fn()} onOpen={vi.fn()} />);
    await userEvent.click(await screen.findByRole('button', { name: 'Delete Budget' }));
    expect(api.deleteMeeting).not.toHaveBeenCalled();
  });

  it('shows an empty state', async () => {
    vi.mocked(api.listMeetings).mockResolvedValue([]);
    render(<MeetingList user={alice} onNew={vi.fn()} onOpen={vi.fn()} />);
    expect(await screen.findByText(/No meetings yet/)).toBeVisible();
  });
});

describe('helpers', () => {
  it('isEmail needs an @ and a dot after it', () => {
    expect(isEmail('Aasha35gmail.com')).toBe(false);
    expect(isEmail('a@b')).toBe(false);
    expect(isEmail(' Aasha35@gmail.com ')).toBe(true);
  });

  it('friendlyProcessingError replaces decoder text and keeps other messages', () => {
    const raw = 'Could not decode audio file (Error opening input files: Invalid data found when processing input).';
    expect(friendlyProcessingError(raw)).toMatch(/could not be read as audio/);
    expect(friendlyProcessingError('No speech was detected in the recording.')).toMatch(/No speech was detected/);
    expect(friendlyProcessingError('Transcription failed for this recording.')).toBe('Transcription failed for this recording.');
    expect(friendlyProcessingError(undefined)).toMatch(/Something went wrong/);
  });
});
