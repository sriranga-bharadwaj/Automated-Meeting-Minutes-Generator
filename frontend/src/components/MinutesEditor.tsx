import { useCallback, useEffect, useRef, useState } from 'react';
import { api, ApiError } from '../api';
import type { ExportFormat, Minutes } from '../types';
import { isLowConfidence, moveItem, uid } from '../utils';

interface Props { meetingId: string; onNew: () => void }
type Save = 'idle' | 'saving' | 'saved' | 'error';

function Move<T>({ list, i, set }: { list: T[]; i: number; set: (l: T[]) => void }) {
  return (
    <span className="mv">
      <button className="ghost" aria-label="Move up" disabled={i === 0} onClick={() => set(moveItem(list, i, -1))}>↑</button>
      <button className="ghost" aria-label="Move down" disabled={i === list.length - 1} onClick={() => set(moveItem(list, i, 1))}>↓</button>
    </span>
  );
}

export default function MinutesEditor({ meetingId, onNew }: Props) {
  const [m, setM] = useState<Minutes | null>(null);
  const [loadError, setLoadError] = useState('');
  const [save, setSave] = useState<Save>('idle');
  const [saveError, setSaveError] = useState('');
  const [exporting, setExporting] = useState<ExportFormat | null>(null);
  const [exportError, setExportError] = useState('');
  const dirty = useRef(false);
  const version = useRef(1);

  const load = useCallback(async () => {
    setLoadError('');
    setM(null);
    try {
      const data = await api.getMinutes(meetingId);
      version.current = data.version;
      setM(data);
    } catch (e) {
      setLoadError(e instanceof ApiError ? e.message : 'Could not load the minutes.');
    }
  }, [meetingId]);
  useEffect(() => { load(); }, [load]);

  // autosave 800 ms after the last edit
  useEffect(() => {
    if (!m || !dirty.current) return;
    setSave('saving');
    const t = setTimeout(async () => {
      try {
        const r = await api.saveMinutes(meetingId, { ...m, version: version.current });
        version.current = r.version;
        dirty.current = false;
        setSaveError('');
        setSave('saved');
      } catch (e) {
        setSave('error');
        setSaveError(e instanceof ApiError ? e.message : 'Could not save your changes.');
      }
    }, 800);
    return () => clearTimeout(t);
  }, [m, meetingId]);

  const edit = (fn: (x: Minutes) => Minutes) => { dirty.current = true; setM((cur) => (cur ? fn(cur) : cur)); };

  async function doExport(f: ExportFormat) {
    if (!m) return;
    setExporting(f);
    setExportError('');
    try { await api.exportMinutes(meetingId, m, f); }
    catch (e) { setExportError(e instanceof ApiError ? e.message : 'Export failed. Please try again.'); }
    finally { setExporting(null); }
  }

  if (loadError) return (
    <div className="card center">
      <div className="banner error" role="alert">{loadError}</div>
      <button onClick={load}>Try again</button>
    </div>
  );
  if (!m) return <div className="card center" aria-busy="true"><div className="spinner" /><p className="muted">Loading minutes…</p></div>;

  const owners = ['Unassigned', ...m.attendees.map((a) => a.name)];
  const low = m.actionItems.filter((a) => isLowConfidence(a.confidence)).length + m.decisions.filter((d) => isLowConfidence(d.confidence)).length;

  return (
    <div className="card">
      <div className="head">
        <div>
          <h2>{m.title}</h2>
          <p className="muted">{m.datetime.replace('T', ' ')} · {m.attendees.map((a) => a.name).join(', ')}</p>
        </div>
        <span className={`save ${save}`} aria-live="polite">
          {save === 'saving' ? 'Saving…' : save === 'saved' ? 'All changes saved' : save === 'error' ? 'Not saved' : ''}
        </span>
      </div>
      {saveError && <div className="banner error" role="alert">{saveError} <button className="ghost" onClick={() => edit((x) => ({ ...x }))}>Retry save</button></div>}
      {low > 0 && <div className="banner warn">{low} item{low > 1 ? 's' : ''} below 60% confidence are highlighted. Please review before sharing.</div>}

      <h3>Key discussions</h3>
      {m.topics.map((t, i) => (
        <div className="item" key={t.id}>
          <div className="grow">
            <input aria-label="Topic title" className="bold" value={t.title} onChange={(e) => edit((x) => ({ ...x, topics: x.topics.map((y) => (y.id === t.id ? { ...y, title: e.target.value } : y)) }))} />
            <textarea aria-label="Topic summary" rows={2} value={t.summary} onChange={(e) => edit((x) => ({ ...x, topics: x.topics.map((y) => (y.id === t.id ? { ...y, summary: e.target.value } : y)) }))} />
          </div>
          <Move list={m.topics} i={i} set={(l) => edit((x) => ({ ...x, topics: l }))} />
          <button className="ghost danger" aria-label="Delete topic" onClick={() => edit((x) => ({ ...x, topics: x.topics.filter((y) => y.id !== t.id) }))}>✕</button>
        </div>
      ))}
      <button className="ghost" onClick={() => edit((x) => ({ ...x, topics: [...x.topics, { id: uid(), title: '', summary: '' }] }))}>+ Add topic</button>

      <h3>Decisions</h3>
      {m.decisions.map((d, i) => (
        <div className={`item ${isLowConfidence(d.confidence) ? 'low' : ''}`} key={d.id}>
          <input className="grow" aria-label="Decision" value={d.statement} onChange={(e) => edit((x) => ({ ...x, decisions: x.decisions.map((y) => (y.id === d.id ? { ...y, statement: e.target.value } : y)) }))} />
          <span className="conf" title="Model confidence">{Math.round(d.confidence * 100)}%</span>
          <Move list={m.decisions} i={i} set={(l) => edit((x) => ({ ...x, decisions: l }))} />
          <button className="ghost danger" aria-label="Delete decision" onClick={() => edit((x) => ({ ...x, decisions: x.decisions.filter((y) => y.id !== d.id) }))}>✕</button>
        </div>
      ))}
      <button className="ghost" onClick={() => edit((x) => ({ ...x, decisions: [...x.decisions, { id: uid(), statement: '', confidence: 1 }] }))}>+ Add decision</button>

      <h3>Action items</h3>
      <div className="scroll">
        <table>
          <thead><tr><th>Task</th><th>Owner</th><th>Deadline</th><th>Status</th><th>Conf.</th><th /></tr></thead>
          <tbody>
            {m.actionItems.map((a, i) => {
              const up = (patch: Partial<typeof a>) => edit((x) => ({ ...x, actionItems: x.actionItems.map((y) => (y.id === a.id ? { ...y, ...patch } : y)) }));
              return (
                <tr key={a.id} className={isLowConfidence(a.confidence) ? 'low' : ''}>
                  <td><input aria-label="Task" value={a.task} onChange={(e) => up({ task: e.target.value })} /></td>
                  <td>
                    <select aria-label="Owner" value={a.owner} onChange={(e) => up({ owner: e.target.value })}>
                      {!owners.includes(a.owner) && <option>{a.owner}</option>}
                      {owners.map((o) => <option key={o}>{o}</option>)}
                    </select>
                  </td>
                  <td><input aria-label="Deadline" type="date" value={a.due} onChange={(e) => up({ due: e.target.value })} /></td>
                  <td>
                    <select aria-label="Status" value={a.status} onChange={(e) => up({ status: e.target.value as 'Open' | 'Done' })}>
                      <option>Open</option><option>Done</option>
                    </select>
                  </td>
                  <td><span className="conf" title={isLowConfidence(a.confidence) ? 'Low confidence, please review' : 'Model confidence'}>{isLowConfidence(a.confidence) ? '⚠ ' : ''}{Math.round(a.confidence * 100)}%</span></td>
                  <td className="nowrap">
                    <Move list={m.actionItems} i={i} set={(l) => edit((x) => ({ ...x, actionItems: l }))} />
                    <button className="ghost danger" aria-label="Delete action item" onClick={() => edit((x) => ({ ...x, actionItems: x.actionItems.filter((y) => y.id !== a.id) }))}>✕</button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <button className="ghost" onClick={() => edit((x) => ({ ...x, actionItems: [...x.actionItems, { id: uid(), task: '', owner: 'Unassigned', due: '', status: 'Open', confidence: 1 }] }))}>+ Add action item</button>

      <h3>Export</h3>
      {exportError && <div className="banner error" role="alert">{exportError}</div>}
      <div className="actions left no-print">
        {([['docx', 'Word (DOCX)'], ['pdf', 'PDF'], ['md', 'Markdown']] as [ExportFormat, string][]).map(([f, label]) => (
          <button key={f} className="ghost" disabled={exporting !== null} onClick={() => doExport(f)}>{exporting === f ? 'Exporting…' : label}</button>
        ))}
        <span className="grow" />
        <button onClick={onNew}>Start a new meeting</button>
      </div>
    </div>
  );
}
