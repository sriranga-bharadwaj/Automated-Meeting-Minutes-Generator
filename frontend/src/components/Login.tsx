import { useState } from 'react';
import { ApiError, auth } from '../api';
import type { User } from '../types';
import { isEmail } from '../utils';

interface Props { onLoggedIn: (user: User) => void }

export default function Login({ onLoggedIn }: Props) {
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [errors, setErrors] = useState<{ name?: string; email?: string; password?: string }>({});
  const [serverError, setServerError] = useState('');
  const [busy, setBusy] = useState(false);
  const register = mode === 'register';

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const found: typeof errors = {};
    if (register && !name.trim()) found.name = 'Name is required.';
    if (!isEmail(email)) found.email = 'Enter a valid email address, for example name@example.com.';
    if (!password) found.password = 'Password is required.';
    else if (register && password.length < 8) found.password = 'Use at least 8 characters.';
    setErrors(found);
    setServerError('');
    if (Object.keys(found).length) return;

    setBusy(true);
    try {
      const user = register
        ? await auth.register(name.trim(), email.trim(), password)
        : await auth.login(email.trim(), password);
      onLoggedIn(user);
    } catch (err) {
      setServerError(err instanceof ApiError ? err.message : 'Could not sign in. Please try again.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card login" onSubmit={submit} noValidate>
      <h2>{register ? 'Create an account' : 'Log in'}</h2>
      {register && (
        <>
          <label htmlFor="login-name">Name</label>
          <input id="login-name" value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" aria-invalid={!!errors.name} />
          {errors.name && <small className="field-error">{errors.name}</small>}
        </>
      )}
      <label htmlFor="login-email">Email</label>
      <input id="login-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" aria-invalid={!!errors.email} />
      {errors.email && <small className="field-error">{errors.email}</small>}
      <label htmlFor="login-password">Password</label>
      <input id="login-password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete={register ? 'new-password' : 'current-password'} aria-invalid={!!errors.password} />
      {errors.password && <small className="field-error">{errors.password}</small>}
      {serverError && <div className="banner error" role="alert">{serverError}</div>}
      <div className="actions">
        <button type="submit" disabled={busy}>{busy ? 'Please wait…' : register ? 'Create account' : 'Log in'}</button>
        <button
          type="button"
          className="ghost"
          onClick={() => { setMode(register ? 'login' : 'register'); setErrors({}); setServerError(''); }}
        >
          {register ? 'I already have an account' : 'Create an account'}
        </button>
      </div>
      {register && <p className="muted">The first account created becomes the administrator.</p>}
    </form>
  );
}
