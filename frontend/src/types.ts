export type Status = 'QUEUED' | 'TRANSCRIBING' | 'ANALYSING' | 'READY' | 'FAILED';
export type ExportFormat = 'docx' | 'pdf' | 'md';

export type Role = 'admin' | 'organizer' | 'participant';
export interface User { id: string; name: string; email: string; role: Role }
export interface MeetingSummary {
  id: string;
  title: string;
  status: string; // backend values: created, processed, ...
  created_at: string;
  owner_email?: string | null; // who owns the meeting
  owned?: boolean; // false: the person was invited and can only view it
}

export interface Attendee { name: string; email: string }
export interface MeetingInput {
  title: string;
  datetime: string;
  agenda: string;
  language: 'en' | 'hi';
  attendees: Attendee[];
}
export interface JobStatus { status: Status; stage?: string; progress: number; error?: string }

/** The stretch of the recording an item came from, in seconds. */
export interface Source { start: number; end: number; text: string }

export interface Topic { id: string; title: string; summary: string; source?: Source | null }
export interface Decision { id: string; statement: string; confidence: number; source?: Source | null }
export interface ActionItem {
  id: string;
  task: string;
  owner: string; // attendee name or 'Unassigned'
  due: string; // yyyy-mm-dd or ''
  status: 'Open' | 'Done';
  confidence: number;
  source?: Source | null;
}

export interface TranscriptSegment { start: number; end: number; text: string; speaker: string }
export interface Transcript { language: string | null; text: string; segments: TranscriptSegment[] }
export interface VersionInfo { version: number; saved_at: string | null; saved_by: string | null; current: boolean }
export interface ActionRow {
  meeting_id: string;
  meeting_title: string;
  id: string;
  task: string;
  owner: string;
  due: string;
  status: 'Open' | 'Done';
  overdue: boolean;
  can_edit: boolean; // false for items of meetings the person was only invited to
}
export interface JobRow {
  meeting_id: string;
  title: string;
  owner_email: string | null;
  status: string;
  progress: number;
  error: string | null;
  audio_file: string | null;
  audio_bytes: number | null;
  created_at: string | null;
}
export interface AuditRow { id: number; ts: string | null; actor: string | null; event: string; detail: string }
export interface Minutes {
  version: number;
  title: string;
  datetime: string;
  agenda: string;
  attendees: Attendee[];
  topics: Topic[];
  decisions: Decision[];
  actionItems: ActionItem[];
}
