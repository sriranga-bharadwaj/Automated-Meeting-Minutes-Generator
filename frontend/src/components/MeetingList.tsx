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

  return (
    <div className="card">
      <div className="head">
        <h2>{admin ? 'All meetings' : 'My meetings'}</h2>
        <button onClick={onNew}>+ New meeting</button>
      </div>
      {error && <div className="banner error" role="alert">{error}</div>}
      {meetings === null && !error && <p className="muted">Loading…</p>}
      {meetings !== null && meetings.length === 0 && (
        <p className="muted">No meetings yet. Create one to upload a recording and get minutes.</p>
      )}
      {meetings !== null && meetings.length > 0 && (
        <div className="scroll">
          <table aria-label="Meetings">
            <thead>
              <tr><th>Title</th><th>Created</th><th>Status</th>{admin && <th>Owner</th>}<th /></tr>
            </thead>
            <tbody>
              {meetings.map((m) => (
                <tr key={m.id}>
                  <td className="bold">{m.title}</td>
                  <td className="nowrap">{formatDate(m.created_at)}</td>
                  <td>{statusLabel(m.status)}</td>
                  {admin && <td>{m.owner_email ?? 'Before login existed'}</td>}
                  <td className="nowrap">
                    <button className="ghost" onClick={() => onOpen(m)} aria-label={`Open ${m.title}`}>Open</button>{' '}
                    <button className="ghost danger" onClick={() => remove(m)} aria-label={`Delete ${m.title}`}>Delete</button>
                  </td>
                </tr>
              ))}
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
