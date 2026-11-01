import { useState } from 'react';
import { api, ApiError } from '../api';
import type { MeetingInput } from '../types';
import { cleanAttendees, validateMeeting, type MeetingErrors } from '../utils';

interface Props { onCreated: (id: string, input: MeetingInput) => void }

export default function MeetingForm({ onCreated }: Props) {
  const [m, setM] = useState<MeetingInput>({
    title: '', datetime: '', agenda: '', language: 'en', attendees: [{ name: '', email: '' }],
  });
  const [errors, setErrors] = useState<MeetingErrors>({});
  const [busy, setBusy] = useState(false);
  const [apiError, setApiError] = useState('');

  const setAtt = (i: number, k: 'name' | 'email', v: string) =>
    setM({ ...m, attendees: m.attendees.map((a, j) => (j === i ? { ...a, [k]: v } : a)) });

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const errs = validateMeeting(m);
    setErrors(errs);
    if (Object.keys(errs).length) return;
    setBusy(true);
    setApiError('');
    try {
      const input = { ...m, attendees: cleanAttendees(m.attendees) };
      const { meetingId } = await api.createMeeting(input);
      onCreated(meetingId, input);
    } catch (err) {
      setApiError(err instanceof ApiError ? err.message : 'Could not create the meeting.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card" onSubmit={submit} noValidate>
      <h2>Create a meeting</h2>
      {apiError && <div className="banner error" role="alert">{apiError}</div>}

      <label htmlFor="title">Title</label>
      <input id="title" value={m.title} onChange={(e) => setM({ ...m, title: e.target.value })} placeholder="Sprint 2 review" />
      {errors.title && <p className="field-error">{errors.title}</p>}

      <div className="row">
        <div>
          <label htmlFor="dt">Date and time</label>
          <input id="dt" type="datetime-local" value={m.datetime} onChange={(e) => setM({ ...m, datetime: e.target.value })} />
          {errors.datetime && <p className="field-error">{errors.datetime}</p>}
        </div>
        <div>
          <label htmlFor="lang">Spoken language</label>
          <select id="lang" value={m.language} onChange={(e) => setM({ ...m, language: e.target.value as 'en' | 'hi' })}>
            <option value="en">English</option>
            <option value="hi">Hindi</option>
          </select>
        </div>
      </div>

      <label htmlFor="agenda">Agenda</label>
      <textarea id="agenda" rows={3} value={m.agenda} onChange={(e) => setM({ ...m, agenda: e.target.value })} />

      <label>Attendees</label>
      {m.attendees.map((a, i) => (
        <div className="row att" key={i}>
          <input aria-label={`Attendee ${i + 1} name`} placeholder="Name" value={a.name} onChange={(e) => setAtt(i, 'name', e.target.value)} />
          <input aria-label={`Attendee ${i + 1} email`} placeholder="email@example.com" value={a.email} onChange={(e) => setAtt(i, 'email', e.target.value)} />
          <button type="button" className="ghost" aria-label={`Remove attendee ${i + 1}`}
            disabled={m.attendees.length === 1} onClick={() => setM({ ...m, attendees: m.attendees.filter((_, j) => j !== i) })}>✕</button>
        </div>
      ))}
      {errors.attendees && <p className="field-error">{errors.attendees}</p>}
      <button type="button" className="ghost" onClick={() => setM({ ...m, attendees: [...m.attendees, { name: '', email: '' }] })}>+ Add attendee</button>

      <div className="actions">
        <button type="submit" disabled={busy}>{busy ? 'Creating…' : 'Create meeting and continue'}</button>
      </div>
    </form>
  );
}
