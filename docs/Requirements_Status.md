# Requirements status

Status of every functional (AMG-F), security (AMG-SR) and non-functional (AMG-NF) requirement in the SRS, checked on 19-Nov-2026 against the code, the automated tests and a live browser run (`frontend/scripts/requirements-validation.mjs`, 16 of 16 checks passed; screenshots in `docs/requirements-validation/`).

- **Done** means it works and was tested. **Partly** and **Not done** say what is missing.
- Tests: backend `pytest` (new files `test_security.py`, `test_features.py`, `test_auth.py`, `test_audio_check.py`) and frontend `npm test` (`auth.test.tsx`, `features.test.tsx`).
- The AI-voice recordings are synthetic. Real speech may give worse transcripts and worse minutes.

## Functional requirements

| ID | Requirement | Status | Evidence and notes |
|---|---|---|---|
| F-001 | Register and log in | Done | Login page, Argon2id passwords. **Not done:** email verification (TC-Auth-01 asks for it). |
| F-002 | Role-based access | Done | Admin and user roles; a user gets 403 for another user's meeting (`test_auth.py`, live check). |
| F-003 | Account lockout | Done | 5 wrong passwords lock for 15 minutes; the lock is recorded in the audit log. |
| F-010 | Create meeting | Done | Form with title, date, agenda, language and attendees. |
| F-011 | Upload recording | Done | MP3, WAV, M4A, MP4 (and OGG, WEBM); default limit 500 MB on the `/api/v1` route, 25 MB on the older route the web UI uses. |
| F-012 | Browser recording | Done | Recording option in the upload step. Pause/resume was not tested. |
| F-013 | Validate and normalise audio | Done | File signature check at upload, 16 kHz mono conversion with FFmpeg. Silent audio returns an empty transcript at the transcription step (the processing job then refuses it). |
| F-014 | Processing status | Done | Queued, Transcribing, Analysing, Ready, with Retry on failure. |
| F-020 | Speech to text | Done | Whisper `base`; the real phone clip scores WER 15.4% (misses the 15% target), `small` scores 11.7%. |
| F-021 | Speaker identification | **Not done** | The app cannot tell speakers apart by voice. That needs a pyannote model (gated download, Hugging Face token, PyTorch). What exists: the transcript editor lets a person type a speaker name per segment, with the attendees offered as suggestions. |
| F-022 | Edit transcript | Done | Edit text and speaker per segment, play from any segment, edits persist (`test_features.py`, live check). |
| F-023 | Language selection | Partly | The English/Hindi selector exists and its value is passed to Whisper. No Hindi recording was ever run. |
| F-030 | Key discussions | Done | Topics with title and summary. No time range per topic. |
| F-031 | Decisions | Partly | Found, but the model sometimes misses one (see the system validation report). |
| F-032 | Action items | Done | 5 of 5 found on the real recording with `small`. |
| F-033 | Responsible person | Done | Owner matched to the attendee list; a misheard name can still give a wrong owner. |
| F-034 | Deadlines | Partly | Weekdays and "tomorrow" are turned into dates. "Next Friday" is deliberately left in the task text. A mis-heard weekday gives a wrong date. |
| F-035 | Confidence scores | Partly | Shown for each item; the keyword fallback gives 50%, the AI model 100%. They are not computed per item. |
| F-040 | Generate minutes | Done | |
| F-041 | Editable minutes | Done | Autosave, move, add, delete. |
| F-042 | Source linking | Done | Each topic, decision and action item shows "▶ m:ss" and plays the recording from the matching segment. The match is by shared words, so an item with no match gets no link. |
| F-043 | Version history | Done | Each save keeps the old version; list and restore (restoring saves a new version). |
| F-044 | Export | Done | Word, PDF, Markdown. |
| F-045 | Share by email | Done | Sends the minutes as an attachment through an SMTP server (`SMTP_HOST` etc.). Tested with a local test mail server (`backend/scripts/smtp_sink.py`); not tested against a real mail provider. |
| F-050 | Action dashboard | Done | Action tracker page across all meetings, with status, owner and overdue filters and a Done checkbox. |
| F-051 | Reminders and status | Done | An hourly background job (and an admin button) emails the owner of an item due within a day or overdue, once per item. Needs SMTP and an email address for the owner in the attendee list. |
| F-060 | Job monitoring | Done | Admin console shows each meeting's job state, recording, and problem. There is no queue or retry control. |
| F-061 | Delete and retention | Done | Owner or admin can delete a meeting and its recording. Set `RETENTION_DAYS` or use the admin button to purge old meetings. |

## Security requirements

| ID | Requirement | Status | Evidence and notes |
|---|---|---|---|
| SR-001 | TLS 1.2 or higher | Partly | `scripts/make_dev_cert.py` plus `uvicorn --ssl-keyfile --ssl-certfile` serves HTTPS; verified: TLS 1.2 accepted, TLS 1.1 refused, HSTS sent. `FORCE_HTTPS=true` redirects HTTP to HTTPS. A real certificate and the service-to-service links are the deployer's job; the default run is plain HTTP on localhost. |
| SR-002 | AES-256 at rest | Done | Audio files and the transcript, segment and minutes columns are encrypted with AES-256-GCM. Verified on disk: the recording starts with the encryption marker and no transcript words appear in `ammg.db`. The key is in `AMMG_DATA_KEY` or `backend/.ammg_datakey`; **if the key is lost the data cannot be read.** Meeting titles and attendee names are not encrypted. |
| SR-003 | Argon2id or bcrypt hashes | Done | Argon2id; older scrypt hashes upgrade at the next login. |
| SR-004 | JWT 30 min, rotating refresh, logout invalidates | Done | Access token 30 minutes, refresh token rotates on use, logout and refresh-token reuse revoke the session (live check). |
| SR-005 | Per-meeting access check | Done | Server checks the owner on every meeting route; tested for every new route. |
| SR-006 | Upload validation, virus scan, random names | Partly | Done: content type check, file signature check, size limit, PyAV decode check, random file names. **Virus scan:** runs ClamAV (`clamscan`) when installed; it is not installed on this machine, so the step is skipped and was only tested with a stand-in. |
| SR-007 | Rate limiting | Done | 100 requests per minute per user, 10 login attempts per minute per address, HTTP 429 with Retry-After. In-memory, so one server process only. |
| SR-008 | Tamper-evident audit log, one year | Done | Hash-chained table of logins, failures, logouts, shares, exports, deletes, role changes, transcript edits, restores and purges; admin screen and a verify button; rows older than a year are purged. The log lives in the same database, so someone with database access could rewrite the whole chain. |
| SR-009 | Self-hosted models | Done | Whisper and Ollama run locally; nothing is sent to a third party. |
| SR-010 | Sanitising, CSP and security headers | Done | HTML tags and control characters are removed from stored text; the API sends CSP, nosniff, frame, referrer and permissions headers; the production frontend build carries a CSP meta tag and the dev server sends nosniff/frame/referrer headers. React escapes all displayed text. |

## Non-functional requirements

| ID | Requirement | Status |
|---|---|---|
| NF-001 | Performance | Measured on 5 recordings, faster than real time (0.07 to 0.45x). Not the 10 recordings in the plan. |
| NF-002 | Accuracy | WER measured. Extraction (precision and recall) checked by hand on 2 clips, not scored with a script. |
| NF-003 | Reliability | Not measured. |
| NF-004 | Usability | Not measured (no survey). |
| NF-005 | Scalability | Not measured (one background worker at a time). |
| NF-006 | Compatibility | Tested in Chrome only. |
| NF-007 | Maintainability | Test suites exist; coverage report for the frontend `utils.ts` only. |
| NF-008 | Accessibility | An axe check runs in the existing browser test; no manual audit. |

## What is still not complete
1. **F-021** automatic speaker detection.
2. **SR-001** production TLS, **SR-006** virus scanning: only the hooks and development setup exist.
3. **F-001** email verification, **F-023** Hindi, **F-031/F-034/F-035** quality of decisions, deadlines and confidence.
4. The non-functional measurements above.
