import { useState } from 'react';
import { USE_MOCK } from './api';
import AudioStep from './components/AudioStep';
import MeetingForm from './components/MeetingForm';
import MinutesEditor from './components/MinutesEditor';
import Processing from './components/Processing';
import type { MeetingInput } from './types';

const STEPS = ['Create meeting', 'Upload or record', 'Review minutes'];

export default function App() {
  const [step, setStep] = useState(0);
  const [meetingId, setMeetingId] = useState('');
  const [uploaded, setUploaded] = useState(false);
  const [ready, setReady] = useState(false);

  const reset = () => { setStep(0); setMeetingId(''); setUploaded(false); setReady(false); };
  const created = (id: string, _input: MeetingInput) => { setMeetingId(id); setStep(1); };
  const onUploaded = () => { setUploaded(true); setStep(2); };

  return (
    <div className="app">
      <header className="no-print">
        <h1>Meeting Minutes Generator</h1>
        {USE_MOCK && <span className="pill" title="Set VITE_USE_MOCK=false to use the FastAPI backend">Demo mode</span>}
      </header>
      <nav className="steps no-print" aria-label="Progress">
        {STEPS.map((s, i) => (
          <div key={s} className={i < step ? 'done' : i === step ? 'now' : ''} aria-current={i === step ? 'step' : undefined}>
            <span>{i < step ? '✓' : i + 1}</span> {s}
          </div>
        ))}
      </nav>
      <main>
        {step === 0 && <MeetingForm onCreated={created} />}
        {step === 1 && <AudioStep meetingId={meetingId} onUploaded={onUploaded} />}
        {step === 2 && uploaded && (ready
          ? <MinutesEditor meetingId={meetingId} onNew={reset} />
          : <Processing meetingId={meetingId} onReady={() => setReady(true)} />)}
      </main>
    </div>
  );
}
