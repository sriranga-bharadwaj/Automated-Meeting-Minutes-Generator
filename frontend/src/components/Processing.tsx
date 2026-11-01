import { useEffect, useRef, useState } from 'react';
import { api, ApiError } from '../api';
import type { JobStatus, Status } from '../types';

interface Props { meetingId: string; onReady: () => void }
const STAGES: { key: Status; label: string }[] = [
  { key: 'QUEUED', label: 'Queued' },
  { key: 'TRANSCRIBING', label: 'Transcribing' },
  { key: 'ANALYSING', label: 'Analysing' },
  { key: 'READY', label: 'Ready' },
];

export default function Processing({ meetingId, onReady }: Props) {
  const [job, setJob] = useState<JobStatus>({ status: 'QUEUED', progress: 0 });
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0); // bump to restart polling after Retry
  const readyRef = useRef(onReady);
  readyRef.current = onReady;

  useEffect(() => {
    let stop = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const s = await api.getStatus(meetingId);
        if (stop) return;
        setJob(s);
        setError('');
        if (s.status === 'READY') return readyRef.current();
        if (s.status === 'FAILED') return; // stop polling, show retry
      } catch (e) {
        if (stop) return;
        setError(e instanceof ApiError ? e.message : 'Lost connection while checking status.');
      }
      timer = setTimeout(poll, 1500);
    }
    poll();
    return () => { stop = true; clearTimeout(timer); };
  }, [meetingId, attempt]);

  async function retry() {
    try {
      await api.retry(meetingId);
      setJob({ status: 'QUEUED', progress: 0 });
      setAttempt((a) => a + 1);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Retry failed.');
    }
  }

  const failed = job.status === 'FAILED';
  const idx = STAGES.findIndex((s) => s.key === job.status);
  return (
    <div className="card center">
      <h2>{failed ? 'Processing failed' : 'Generating your minutes'}</h2>
      {error && <div className="banner error" role="alert">{error} <small>(will keep trying)</small></div>}
      {failed ? (
        <>
          <div className="banner error" role="alert">{job.error ?? 'Something went wrong while processing the recording.'}</div>
          <button onClick={retry}>Retry</button>
        </>
      ) : (
        <>
          <ol className="stages">
            {STAGES.map((s, i) => (
              <li key={s.key} className={i < idx ? 'done' : i === idx ? 'now' : ''}>{s.label}</li>
            ))}
          </ol>
          <div className="bar" role="progressbar" aria-valuenow={job.progress} aria-valuemin={0} aria-valuemax={100}>
            <div style={{ width: `${job.progress}%` }} />
          </div>
          <p className="muted">{job.stage ?? 'Starting…'} ({job.progress}%)</p>
        </>
      )}
    </div>
  );
}
