import { useEffect, useState } from 'react';
import { api, ApiError } from '../api';
import type { MeetingSummary, User } from '../types';

interface Props {
  user: User;
  onNew: () => void;
  onOpen: (meeting: MeetingSummary) => void;
}

const STATUS_LABEL: Record<string, string> = {
  created: 'Waiting for audio',
  processed: 'Minutes ready',
};
export const statusLabel = (s: string) => STATUS_LABEL[s] ?? 'Processing or failed';

function formatDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}

export default function MeetingList({ user, onNew, onOpen }: Props) {
  const [meetings, setMeetings] = useState<MeetingSummary[] | null>(null);
  const [users, setUsers] = useState<User[]>([]);
  const [error, setError] = useState('');
  const admin = user.role === 'admin';
  const canCreate = user.role !== 'participant';

  async function load() {
    try {
      setMeetings(await api.listMeetings());
      if (admin) setUsers(await api.listUsers());
      setError('');
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not load your meetings.');
    }
  }
  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, []);

  async function remove(m: MeetingSummary) {
    if (!window.confirm(`Delete "${m.title}" and its recording? This cannot be undone.`)) return;
    try {
      await api.deleteMeeting(m.id);
      setMeetings((list) => (list ?? []).filter((x) => x.id !== m.id));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not delete the meeting.');
    }
  }

  const heading = admin ? 'All meetings' : canCreate ? 'My meetings' : 'Meetings shared with me';
  const emptyText = canCreate
    ? 'No meetings yet. Create one to upload a recording and get minutes.'
    : 'No meetings yet. Meetings appear here when an organizer adds your email address as an attendee.';

  return (
    <div className="card">
      <div className="head">
        <h2>{heading}</h2>
        {canCreate && <button onClick={onNew}>+ New meeting</button>}
      </div>
      {error && <div className="banner error" role="alert">{error}</div>}
      {meetings === null && !error && <p className="muted">Loading…</p>}
      {meetings !== null && meetings.length === 0 && <p className="muted">{emptyText}</p>}
      {meetings !== null && meetings.length > 0 && (
        <div className="scroll">
          <table aria-label="Meetings">
            <thead>
              <tr><th>Title</th><th>Created</th><th>Status</th><th>{admin ? 'Owner' : 'Access'}</th><th /></tr>
            </thead>
            <tbody>
              {meetings.map((m) => {
                const owned = m.owned !== false;
                return (
                  <tr key={m.id}>
                    <td className="bold">{m.title}</td>
                    <td className="nowrap">{formatDate(m.created_at)}</td>
                    <td>{statusLabel(m.status)}</td>
                    <td>
                      {admin
                        ? (m.owner_email ?? 'Before login existed')
                        : owned ? 'Owner' : <>Invited{m.owner_email ? <span className="muted"> by {m.owner_email}</span> : null}</>}
                    </td>
                    <td className="nowrap">
                      <button className="ghost" onClick={() => onOpen(m)} aria-label={`Open ${m.title}`}>{owned ? 'Open' : 'View'}</button>{' '}
                      {owned && <button className="ghost danger" onClick={() => remove(m)} aria-label={`Delete ${m.title}`}>Delete</button>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {admin && users.length > 0 && (
        <>
          <h3>Users</h3>
          <div className="scroll">
            <table aria-label="Users">
              <thead><tr><th>Name</th><th>Email</th><th>Role</th></tr></thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.id}><td>{u.name}</td><td>{u.email}</td><td>{u.role}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
