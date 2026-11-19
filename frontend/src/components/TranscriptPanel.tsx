import { useEffect, useRef, useState } from 'react';
import { api, ApiError } from '../api';
import type { TranscriptSegment } from '../types';
import { formatTime } from '../utils';

interface Props {
  meetingId: string;
  speakers: string[];                       // attendee names offered as speaker labels
  seek: { time: number; n: number } | null; // set by the minutes: "play from here"
}

/** The recording with its transcript: click a segment to hear it, edit the text and speaker. */
export default function TranscriptPanel({ meetingId, speakers, seek }: Props) {
  const [segments, setSegments] = useState<TranscriptSegment[] | null>(null);
  const [audio, setAudio] = useState('');
  const [error, setError] = useState('');
  const [saved, setSaved] = useState<'idle' | 'saving' | 'saved'>('idle');
  const [now, setNow] = useState(0);
  const player = useRef<HTMLAudioElement>(null);

  useEffect(() => {
    let url = '';
    let stop = false;
    (async () => {
      try {
        const t = await api.getTranscript(meetingId);
        if (!stop) setSegments(t.segments);
      } catch (e) {
        if (!stop) setError(e instanceof ApiError ? e.message : 'Could not load the transcript.');
      }
      try {
        url = await api.audioUrl(meetingId);
        if (!stop) setAudio(url);
      } catch { /* the transcript is still useful without playback */ }
    })();
    return () => { stop = true; if (url) URL.revokeObjectURL(url); };
  }, [meetingId]);

  const play = (time: number) => {
    const el = player.current;
    if (!el) return;
    el.currentTime = time;
    void el.play().catch(() => { /* the browser may block autoplay until the person clicks */ });
  };
  useEffect(() => { if (seek) play(seek.time); }, [seek]);

  const change = (i: number, patch: Partial<TranscriptSegment>) => {
    setSaved('idle');
    setSegments((list) => (list ? list.map((s, j) => (j === i ? { ...s, ...patch } : s)) : list));
  };

  async function save() {
    if (!segments) return;
    setSaved('saving');
    setError('');
    try {
      await api.saveTranscript(meetingId, segments);
      setSaved('saved');
    } catch (e) {
      setSaved('idle');
      setError(e instanceof ApiError ? e.message : 'Could not save the transcript.');
    }
  }

  return (
    <section aria-label="Recording and transcript">
      <h3>Recording and transcript</h3>
      {error && <div className="banner error" role="alert">{error}</div>}
      {audio && <audio ref={player} controls src={audio} onTimeUpdate={(e) => setNow(e.currentTarget.currentTime)} style={{ width: '100%' }} />}
      {segments === null && !error && <p className="muted">Loading transcript…</p>}
      {segments !== null && (
        <>
          <datalist id="speaker-names">{speakers.map((s) => <option key={s} value={s} />)}</datalist>
          <ol className="transcript">
            {segments.map((s, i) => (
              <li key={i} className={now >= s.start && now < s.end ? 'now' : ''}>
                <button className="ghost" onClick={() => play(s.start)} aria-label={`Play from ${formatTime(s.start)}`}>▶ {formatTime(s.start)}</button>
                <input
                  className="speaker" list="speaker-names" placeholder="Speaker" aria-label={`Speaker for segment ${i + 1}`}
                  value={s.speaker} onChange={(e) => change(i, { speaker: e.target.value })}
                />
                <textarea
                  rows={2} aria-label={`Text of segment ${i + 1}`} value={s.text}
                  onChange={(e) => change(i, { text: e.target.value })}
                />
              </li>
            ))}
          </ol>
          <div className="actions left no-print">
            <button onClick={save} disabled={saved === 'saving'}>{saved === 'saving' ? 'Saving…' : 'Save transcript'}</button>
            {saved === 'saved' && <span className="save" aria-live="polite">Transcript saved</span>}
            <span className="muted">Speaker names are typed by hand; the app does not detect speakers by voice.</span>
          </div>
        </>
      )}
    </section>
  );
}
