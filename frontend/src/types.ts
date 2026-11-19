export type Status = 'QUEUED' | 'TRANSCRIBING' | 'ANALYSING' | 'READY' | 'FAILED';
export type ExportFormat = 'docx' | 'pdf' | 'md';

export type Role = 'admin' | 'user';
export interface User { id: string; name: string; email: string; role: Role }
export interface MeetingSummary {
  id: string;
  title: string;
  status: string; // backend values: created, processed, ...
  created_at: string;
  owner_email?: string | null; // only filled in for administrators
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

export interface Topic { id: string; title: string; summary: string }
export interface Decision { id: string; statement: string; confidence: number }
export interface ActionItem {
  id: string;
  task: string;
  owner: string; // attendee name or 'Unassigned'
  due: string; // yyyy-mm-dd or ''
  status: 'Open' | 'Done';
  confidence: number;
}
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
