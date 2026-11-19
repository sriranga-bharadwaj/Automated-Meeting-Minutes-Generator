import { useEffect, useState } from 'react';
import { USE_MOCK, auth, currentUser } from './api';
import ActionTracker from './components/ActionTracker';
import AdminConsole from './components/AdminConsole';
import AudioStep from './components/AudioStep';
import Login from './components/Login';
import MeetingForm from './components/MeetingForm';
import MeetingList from './components/MeetingList';
import MinutesEditor from './components/MinutesEditor';
import Processing from './components/Processing';
import type { MeetingInput, MeetingSummary, User } from './types';

const STEPS = ['Create meeting', 'Upload or record', 'Review minutes'];

export default function App() {
  // The offline demo (VITE_USE_MOCK=true) has no accounts, so it skips login and the meeting list.
  const loginOn = !USE_MOCK;
  const [user, setUser] = useState<User | null>(() => (loginOn ? currentUser() : null));
  const [view, setView] = useState<'list' | 'wizard' | 'actions' | 'admin'>(loginOn ? 'list' : 'wizard');
  const [step, setStep] = useState(0);
  const [meetingId, setMeetingId] = useState('');
  const [uploaded, setUploaded] = useState(false);
  const [ready, setReady] = useState(false);

  // api.ts announces this when the server rejects the saved token.
  useEffect(() => {
    const onLogout = () => { setUser(null); setView('list'); };
    window.addEventListener('ammg-logout', onLogout);
    return () => window.removeEventListener('ammg-logout', onLogout);
  }, []);

  const reset = () => { setStep(0); setMeetingId(''); setUploaded(false); setReady(false); };
  const startNew = () => { reset(); setView('wizard'); };
  const created = (id: string, _input: MeetingInput) => { setMeetingId(id); setStep(1); };
  const onUploaded = () => { setUploaded(true); setStep(2); };
  const logout = () => { void auth.logout(); setUser(null); reset(); setView('list'); };
  // The tracker only knows the meeting id; its minutes are ready, so open them directly.
  const openById = (id: string) => open({ id, title: '', status: 'processed', created_at: '' });

  // Reopen a meeting from the list at the step that matches how far it got.
  const open = (m: MeetingSummary) => {
    setMeetingId(m.id);
    if (m.status === 'created') { setUploaded(false); setReady(false); setStep(1); }
    else if (m.status === 'processed') { setUploaded(true); setReady(true); setStep(2); }
    else { setUploaded(true); setReady(false); setStep(2); }
    setView('wizard');
  };

  return (
    <div className="app">
      <header className="no-print">
        <h1>Meeting Minutes Generator</h1>
        {USE_MOCK && <span className="pill" title="Set VITE_USE_MOCK=false to use the FastAPI backend">Demo mode</span>}
        {loginOn && user && (
          <div className="userbar">
            <nav aria-label="Main" className="mainnav">
              <button className={view === 'list' || view === 'wizard' ? 'ghost active' : 'ghost'} onClick={() => setView('list')}>{user.role === 'admin' ? 'All meetings' : 'My meetings'}</button>
              <button className={view === 'actions' ? 'ghost active' : 'ghost'} onClick={() => setView('actions')}>Action tracker</button>
              {user.role === 'admin' && <button className={view === 'admin' ? 'ghost active' : 'ghost'} onClick={() => setView('admin')}>Admin console</button>}
            </nav>
            <span className="who">{user.name}</span>
            <span className="pill role">{user.role}</span>
            <button className="ghost" onClick={logout}>Log out</button>
          </div>
        )}
      </header>
      <main>
        {loginOn && !user && <Login onLoggedIn={(u) => { setUser(u); setView('list'); }} />}
        {loginOn && user && view === 'list' && <MeetingList user={user} onNew={startNew} onOpen={open} />}
        {loginOn && user && view === 'actions' && <ActionTracker onOpenMeeting={openById} />}
        {loginOn && user && user.role === 'admin' && view === 'admin' && <AdminConsole me={user} />}
        {(!loginOn || (user && view === 'wizard')) && (
          <>
            <nav className="steps no-print" aria-label="Progress">
              {STEPS.map((s, i) => (
                <div key={s} className={i < step ? 'done' : i === step ? 'now' : ''} aria-current={i === step ? 'step' : undefined}>
                  <span>{i < step ? '✓' : i + 1}</span> {s}
                </div>
              ))}
            </nav>
            {step === 0 && <MeetingForm onCreated={created} />}
            {step === 1 && <AudioStep meetingId={meetingId} onUploaded={onUploaded} />}
            {step === 2 && uploaded && (ready
              ? <MinutesEditor meetingId={meetingId} onNew={startNew} />
              : <Processing meetingId={meetingId} onReady={() => setReady(true)} />)}
          </>
        )}
      </main>
    </div>
  );
}
