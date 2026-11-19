import { useCallback, useEffect, useState } from 'react';
import { api, ApiError } from '../api';
import type { AuditRow, JobRow, Role, User } from '../types';

interface Props { me: User }

/** For administrators: processing jobs, users and roles, the audit log, reminders and retention. */
export default function AdminConsole({ me }: Props) {
  const [jobs, setJobs] = useState<JobRow[] | null>(null);
  const [users, setUsers] = useState<User[]>([]);
  const [audit, setAudit] = useState<AuditRow[]>([]);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [days, setDays] = useState('90');

  const load = useCallback(async () => {
    try {
      const [j, u, a] = await Promise.all([api.adminJobs(), api.listUsers(), api.adminAudit()]);
      setJobs(j); setUsers(u); setAudit(a);
      setError('');
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not load the admin console.');
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  async function run(action: () => Promise<string>) {
    setNotice(''); setError('');
    try { setNotice(await action()); await load(); }
    catch (e) { setError(e instanceof ApiError ? e.message : 'That did not work.'); }
  }

  const setRole = (u: User, role: Role) => run(async () => { await api.changeRole(u.id, role); return `${u.email} is now ${role}.`; });
  const verify = () => run(async () => {
    const r = await api.verifyAudit();
    return r.intact ? 'The audit log is intact.' : `The audit log was changed: the first bad entry is #${r.first_bad_id}.`;
  });
  const retention = () => run(async () => {
    const n = Number(days);
    if (!Number.isInteger(n) || n < 1) throw new ApiError('INVALID', 'Enter a whole number of days.');
    if (!window.confirm(`Delete every meeting older than ${n} days, with its recording? This cannot be undone.`)) return 'Nothing was deleted.';
    const r = await api.runRetention(n);
    return `Deleted ${r.removed} meeting(s) older than ${r.days} days.`;
  });
  const reminders = () => run(async () => {
    const r = await api.runReminders();
    return `Reminders sent: ${r.sent}, skipped: ${r.skipped}, failed: ${r.failed}.`;
  });

  return (
    <div className="card">
      <div className="head"><h2>Admin console</h2><button className="ghost" onClick={load}>Refresh</button></div>
      {error && <div className="banner error" role="alert">{error}</div>}
      {notice && <div className="banner warn" role="status">{notice}</div>}

      <h3>Processing jobs</h3>
      {jobs !== null && jobs.length === 0 && <p className="muted">No meetings yet.</p>}
      {jobs !== null && jobs.length > 0 && (
        <div className="scroll">
          <table aria-label="Processing jobs">
            <thead><tr><th>Meeting</th><th>Owner</th><th>Status</th><th>Recording</th><th>Problem</th></tr></thead>
            <tbody>
              {jobs.map((j) => (
                <tr key={j.meeting_id}>
                  <td className="bold">{j.title}</td><td>{j.owner_email ?? '—'}</td>
                  <td>{j.status} {j.status !== 'READY' && j.status !== 'FAILED' ? `(${j.progress}%)` : ''}</td>
                  <td>{j.audio_file ? `${j.audio_file} (${((j.audio_bytes ?? 0) / 1024 / 1024).toFixed(1)} MB)` : '—'}</td>
                  <td>{j.error ?? ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h3>Users and roles</h3>
      <div className="scroll">
        <table aria-label="Users and roles">
          <thead><tr><th>Name</th><th>Email</th><th>Role</th></tr></thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id}>
                <td>{u.name}</td><td>{u.email}</td>
                <td>
                  <select aria-label={`Role of ${u.email}`} value={u.role} onChange={(e) => setRole(u, e.target.value as Role)} disabled={u.id === me.id}>
                    <option value="admin">admin</option><option value="organizer">organizer</option><option value="participant">participant</option>
                  </select>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h3>Maintenance</h3>
      <div className="row no-print">
        <input aria-label="Retention days" inputMode="numeric" value={days} onChange={(e) => setDays(e.target.value)} style={{ flex: '0 0 90px' }} />
        <button className="ghost danger" onClick={retention}>Delete meetings older than this many days</button>
        <button className="ghost" onClick={reminders}>Send deadline reminders now</button>
      </div>

      <h3>Audit log</h3>
      <div className="actions left no-print"><button className="ghost" onClick={verify}>Check that the log is untouched</button></div>
      <div className="scroll">
        <table aria-label="Audit log">
          <thead><tr><th>When (UTC)</th><th>Who</th><th>Event</th><th>Detail</th></tr></thead>
          <tbody>
            {audit.map((a) => (
              <tr key={a.id}><td className="nowrap">{a.ts?.replace('T', ' ').slice(0, 19)}</td><td>{a.actor ?? '—'}</td><td>{a.event}</td><td>{a.detail}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
