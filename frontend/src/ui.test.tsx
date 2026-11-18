import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import MeetingForm from './components/MeetingForm';
import AudioStep from './components/AudioStep';
import Processing from './components/Processing';
import { api } from './api';
vi.mock('./api', async (original) => ({ ...await original<typeof import('./api')>(), api: { createMeeting: vi.fn(), uploadAudio: vi.fn(), getStatus: vi.fn(), retry: vi.fn() } }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });
describe('UI and usability', () => {
 it('blocks empty forms and explains required details', () => {
  render(<MeetingForm onCreated={vi.fn()} />);
  fireEvent.click(screen.getByRole('button', { name: /Create meeting/ }));
  expect(screen.getByText('Title is required.')).toBeVisible();
  expect(api.createMeeting).not.toHaveBeenCalled();
 });
 it('supports adding and removing attendees without losing the first row', () => {
  render(<MeetingForm onCreated={vi.fn()} />);
  expect(screen.getByRole('button', { name: 'Remove attendee 1' })).toBeDisabled();
  fireEvent.click(screen.getByText('+ Add attendee'));
  expect(screen.getByLabelText('Attendee 2 name')).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: 'Remove attendee 2' }));
  expect(screen.queryByLabelText('Attendee 2 name')).toBeNull();
 });
 it('creates a valid meeting and trims attendee details', async () => {
  vi.mocked(api.createMeeting).mockResolvedValue({ meetingId: 'm1' });
  const created = vi.fn(); render(<MeetingForm onCreated={created} />);
  for (const [label, value] of [['Title', 'Review'], ['Date and time', '2026-11-18T10:00'], ['Attendee 1 name', ' Siddhant '], ['Attendee 1 email', ' s@example.com ']]) fireEvent.change(screen.getByLabelText(label), { target: { value } });
  fireEvent.click(screen.getByRole('button', { name: /Create meeting/ }));
  await waitFor(() => expect(created).toHaveBeenCalledWith('m1', expect.objectContaining({ attendees: [{ name: 'Siddhant', email: 's@example.com' }] })));
 });
 it('rejects unsupported uploads and keeps generation disabled', () => {
  render(<AudioStep meetingId="m1" onUploaded={vi.fn()} />);
  fireEvent.change(screen.getByLabelText('Audio file'), { target: { files: [new File(['text'], 'notes.txt')] } });
  expect(screen.getByRole('alert')).toHaveTextContent('Unsupported');
  expect(screen.getByRole('button', { name: /Upload and generate/ })).toBeDisabled();
 });
 it('shows microphone denial with an upload alternative', async () => {
  Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: { getUserMedia: vi.fn().mockRejectedValue(new Error('denied')) } });
  render(<AudioStep meetingId="m1" onUploaded={vi.fn()} />);
  fireEvent.click(screen.getByRole('tab', { name: /Record in browser/ }));
  fireEvent.click(screen.getByRole('button', { name: 'Start' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('upload a file instead');
 });
 it('advances once processing is ready', async () => {
  vi.mocked(api.getStatus).mockResolvedValue({ status: 'READY', progress: 100 });
  const ready = vi.fn(); render(<Processing meetingId="m1" onReady={ready} />);
  await waitFor(() => expect(ready).toHaveBeenCalledTimes(1));
 });
});
