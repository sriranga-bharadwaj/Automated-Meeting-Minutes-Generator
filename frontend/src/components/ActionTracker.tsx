import { useCallback, useEffect, useState } from 'react';
import { api, ApiError } from '../api';
import type { ActionRow } from '../types';

interface Props { onOpenMeeting: (meetingId: string) => void }

/** Action items from all meetings in one list, with filters and a Done checkbox. */
export default function ActionTracker({ onOpenMeeting }: Props) {
  const [rows, setRows] = useState<ActionRow[] | null>(null);
  const [status, setStatus] = useState('');
  const [owner, setOwner] = useState('');
  const [overdue, setOverdue] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try {
      setRows(await api.listActions({ status, owner: owner.trim(), overdue }));
      setError('');
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not load the action items.');
    }
  }, [status, owner, overdue]);
  useEffect(() => { load(); }, [load]);

  async function toggle(row: ActionRow) {
    const next = row.status === 'Done' ? 'Open' : 'Done';
    // Show the change at once; the list is reloaded from the server afterwards (or on failure).
    setRows((list) => (list ?? []).map((r) => (r.meeting_id === row.meeting_id && r.id === row.id ? { ...r, status: next } : r)));
    try {
      await api.setActionStatus(row.meeting_id, row.id, next);
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not update the action item.');
      await load();
    }
  }

  return (
    <div className="card">
      <div className="head"><h2>Action tracker</h2></div>
      <div className="row no-print" role="search" aria-label="Filter action items">
        <select aria-label="Status filter" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">All statuses</option><option value="Open">Open</option><option value="Done">Done</option>
        </select>
        <input aria-label="Owner filter" placeholder="Owner name" value={owner} onChange={(e) => setOwner(e.target.value)} />
        <label className="check"><input type="checkbox" checked={overdue} onChange={(e) => setOverdue(e.target.checked)} /> Overdue only</label>
      </div>
      {error && <div className="banner error" role="alert">{error}</div>}
      {rows === null && !error && <p className="muted">Loading…</p>}
      {rows !== null && rows.length === 0 && <p className="muted">No action items match.</p>}
      {rows !== null && rows.length > 0 && (
        <div className="scroll">
          <table aria-label="Action items">
            <thead><tr><th>Done</th><th>Task</th><th>Owner</th><th>Deadline</th><th>Meeting</th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={`${r.meeting_id}-${r.id}`} className={r.overdue ? 'low' : ''}>
                  <td><input type="checkbox" aria-label={`Mark "${r.task}" done`} checked={r.status === 'Done'} onChange={() => toggle(r)} /></td>
                  <td className={r.status === 'Done' ? 'muted' : 'bold'}>{r.task}</td>
                  <td>{r.owner}</td>
                  <td className="nowrap">{r.due || '—'} {r.overdue && <span className="pill overdue">overdue</span>}</td>
                  <td><button className="ghost" onClick={() => onOpenMeeting(r.meeting_id)}>{r.meeting_title}</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
