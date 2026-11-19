import { useState } from 'react';
import { api, ApiError } from '../api';
import type { ExportFormat } from '../types';
import { isEmail } from '../utils';

interface Props { meetingId: string; suggestions: string[] }

/** Email the minutes as a Word, PDF or Markdown attachment. */
export default function ShareMinutes({ meetingId, suggestions }: Props) {
  const [emails, setEmails] = useState(suggestions.join(', '));
  const [format, setFormat] = useState<ExportFormat>('pdf');
  const [state, setState] = useState<{ kind: 'idle' | 'sending' | 'ok' | 'error'; text?: string }>({ kind: 'idle' });

  async function send() {
    const list = emails.split(/[,;\s]+/).map((e) => e.trim()).filter(Boolean);
    if (list.length === 0 || !list.every(isEmail)) {
      setState({ kind: 'error', text: 'Enter valid email addresses, separated by commas.' });
      return;
    }
    setState({ kind: 'sending' });
    try {
      const r = await api.shareMinutes(meetingId, list, format);
      setState({ kind: 'ok', text: `Sent to ${r.sent} address${r.sent === 1 ? '' : 'es'}.` });
    } catch (e) {
      setState({ kind: 'error', text: e instanceof ApiError ? e.message : 'The email could not be sent.' });
    }
  }

  return (
    <section aria-label="Share by email">
      <h3>Share by email</h3>
      <div className="row no-print">
        <input aria-label="Email addresses" placeholder="name@example.com, other@example.com" value={emails} onChange={(e) => setEmails(e.target.value)} />
        <select aria-label="Attachment format" value={format} onChange={(e) => setFormat(e.target.value as ExportFormat)} style={{ flex: '0 0 140px' }}>
          <option value="pdf">PDF</option><option value="docx">Word (DOCX)</option><option value="md">Markdown</option>
        </select>
        <button onClick={send} disabled={state.kind === 'sending'} style={{ flex: '0 0 120px' }}>{state.kind === 'sending' ? 'Sending…' : 'Send'}</button>
      </div>
      {state.kind === 'error' && <div className="banner error" role="alert">{state.text}</div>}
      {state.kind === 'ok' && <div className="banner warn" role="status">{state.text}</div>}
    </section>
  );
}
