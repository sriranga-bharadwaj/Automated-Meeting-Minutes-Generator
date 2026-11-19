import { useEffect, useState } from 'react';
import { api, ApiError } from '../api';
import type { VersionInfo } from '../types';

interface Props { meetingId: string; refreshKey: number; onRestored: () => void }

/** Earlier saved versions of the minutes. Restoring one saves it as the newest version. */
export default function VersionHistory({ meetingId, refreshKey, onRestored }: Props) {
  const [versions, setVersions] = useState<VersionInfo[] | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState<number | null>(null);

  async function load() {
    try {
      setVersions(await api.listVersions(meetingId));
      setError('');
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not load the version history.');
    }
  }
  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [meetingId, refreshKey]);

  async function restore(v: VersionInfo) {
    if (!window.confirm(`Restore version ${v.version}? It becomes the newest version; nothing is lost.`)) return;
    setBusy(v.version);
    try {
      await api.restoreVersion(meetingId, v.version);
      await load();
      onRestored();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not restore that version.');
    } finally {
      setBusy(null);
    }
  }

  return (
    <section aria-label="Version history">
      <h3>Version history</h3>
      {error && <div className="banner error" role="alert">{error}</div>}
      {versions !== null && versions.length <= 1 && <p className="muted">Only one version so far. Each change you save adds a version.</p>}
      {versions !== null && versions.length > 1 && (
        <ul className="versions">
          {versions.map((v) => (
            <li key={v.version}>
              <span className="bold">Version {v.version}</span>{' '}
              {v.current ? <span className="pill">current</span> : <span className="muted">{v.saved_at ? new Date(v.saved_at).toLocaleString() : ''} {v.saved_by ? `· ${v.saved_by}` : ''}</span>}
              {!v.current && (
                <button className="ghost" disabled={busy !== null} onClick={() => restore(v)} aria-label={`Restore version ${v.version}`}>
                  {busy === v.version ? 'Restoring…' : 'Restore'}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
