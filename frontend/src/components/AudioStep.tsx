import { useEffect, useRef, useState } from 'react';
import { api, ApiError } from '../api';
import { validateAudio } from '../utils';

interface Props { meetingId: string; onUploaded: () => void }
type Tab = 'upload' | 'record';
type RecState = 'idle' | 'recording' | 'paused' | 'stopped';

const fmt = (s: number) => `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;

export default function AudioStep({ meetingId, onUploaded }: Props) {
  const [tab, setTab] = useState<Tab>('upload');
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState('');
  const [progress, setProgress] = useState<number | null>(null);

  // recorder
  const [rec, setRec] = useState<RecState>('idle');
  const [secs, setSecs] = useState(0);
  const [recUrl, setRecUrl] = useState('');
  const recorder = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);
  const blob = useRef<Blob | null>(null);
  const stream = useRef<MediaStream | null>(null);

  useEffect(() => {
    if (rec !== 'recording') return;
    const t = setInterval(() => setSecs((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, [rec]);
  useEffect(() => () => stream.current?.getTracks().forEach((t) => t.stop()), []);

  const busy = progress !== null;

  function pick(f: File | undefined) {
    if (!f) return;
    const err = validateAudio(f);
    setError(err ?? '');
    setFile(err ? null : f);
  }

  async function startRec() {
    setError('');
    try {
      stream.current = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setError('Microphone access was blocked. Allow the microphone in your browser, or upload a file instead.');
      return;
    }
    chunks.current = [];
    const r = new MediaRecorder(stream.current);
    r.ondataavailable = (e) => e.data.size && chunks.current.push(e.data);
    r.onstop = () => {
      blob.current = new Blob(chunks.current, { type: r.mimeType || 'audio/webm' });
      setRecUrl(URL.createObjectURL(blob.current));
      stream.current?.getTracks().forEach((t) => t.stop());
      setRec('stopped');
    };
    recorder.current = r;
    setSecs(0);
    r.start();
    setRec('recording');
  }
  const pause = () => { recorder.current?.pause(); setRec('paused'); };
  const resume = () => { recorder.current?.resume(); setRec('recording'); };
  const stop = () => recorder.current?.stop();

  async function send(data: Blob, name: string) {
    setError('');
    setProgress(0);
    try {
      await api.uploadAudio(meetingId, data, name, setProgress);
      onUploaded();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Upload failed. Please try again.');
      setProgress(null);
    }
  }

  return (
    <div className="card">
      <h2>Add the meeting audio</h2>
      <div className="tabs" role="tablist">
        <button role="tab" aria-selected={tab === 'upload'} className={tab === 'upload' ? 'active' : ''} onClick={() => setTab('upload')} disabled={busy}>Upload file</button>
        <button role="tab" aria-selected={tab === 'record'} className={tab === 'record' ? 'active' : ''} onClick={() => setTab('record')} disabled={busy}>Record in browser</button>
      </div>
      {error && <div className="banner error" role="alert">{error}</div>}

      {tab === 'upload' && (
        <>
          <div className="drop" onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); pick(e.dataTransfer.files[0]); }}>
            <p>Drag a recording here, or</p>
            <input aria-label="Audio file" type="file" accept=".mp3,.wav,.m4a,.mp4,audio/*,video/mp4" onChange={(e) => pick(e.target.files?.[0])} disabled={busy} />
            <small>MP3, WAV, M4A or MP4, up to 25 MB</small>
          </div>
          {file && <p className="muted">Selected: <b>{file.name}</b> ({(file.size / 1048576).toFixed(1)} MB)</p>}
          <div className="actions">
            <button disabled={!file || busy} onClick={() => file && send(file, file.name)}>{busy ? 'Uploading…' : 'Upload and generate minutes'}</button>
          </div>
        </>
      )}

      {tab === 'record' && (
        <>
          <div className="recorder">
            <div className={`dot ${rec}`} aria-hidden />
            <span className="timer" aria-live="off">{fmt(secs)}</span>
            <span className="muted">{rec === 'idle' ? 'Ready' : rec === 'recording' ? 'Recording' : rec === 'paused' ? 'Paused' : 'Recorded'}</span>
          </div>
          <div className="actions left">
            {(rec === 'idle' || rec === 'stopped') && <button onClick={startRec} disabled={busy}>{rec === 'stopped' ? 'Record again' : 'Start'}</button>}
            {rec === 'recording' && <button className="ghost" onClick={pause}>Pause</button>}
            {rec === 'paused' && <button className="ghost" onClick={resume}>Resume</button>}
            {(rec === 'recording' || rec === 'paused') && <button onClick={stop}>Stop</button>}
          </div>
          {rec === 'stopped' && recUrl && (
            <>
              <audio controls src={recUrl} />
              <div className="actions">
                <button disabled={busy} onClick={() => blob.current && send(blob.current, 'recording.webm')}>{busy ? 'Uploading…' : 'Use this recording'}</button>
              </div>
            </>
          )}
        </>
      )}

      {busy && (
        <div className="progress-wrap" aria-live="polite">
          <div className="bar"><div style={{ width: `${progress}%` }} /></div>
          <small>Uploading {progress}%</small>
        </div>
      )}
    </div>
  );
}
