# Unit Test Report

Run on 20-Nov-2026 on branch `docs/test-reports` (code of PR #19, including roles and invited-meeting access).
Machine: Windows 11, Python 3.12.10, pytest 9.2.0, Node with Vitest 2.1.9.

## Result

| Suite | Command | Tests | Passed | Failed | Skipped |
|---|---|---|---|---|---|
| Backend | `cd backend && python -m pytest` | 226 | 226 | 0 | 0 |
| Frontend | `cd frontend && npm test` | 54 | 54 | 0 | 0 |
| Total | | 280 | 280 | 0 | 0 |

The backend run took 5 minutes 4 seconds, the frontend run 13 seconds. The backend run reported 4 deprecation warnings (`datetime.utcnow()` and the sqlite3 datetime adapter) and no other warnings. The raw results are in `docs/coverage/backend-junit.xml` and `docs/coverage/frontend-junit.xml`.

## Backend tests by file

| File | Tests | What it checks |
|---|---|---|
| `test_api_v1.py` | 16 | The `/api/v1` routes |
| `test_audio_check.py` | 3 | Upload checks: content type, file signature, decoding |
| `test_auth.py` | 13 | Registration, login, lockout, tokens, refresh and logout |
| `test_chunking.py` | 34 | Splitting long transcripts for the minutes generator |
| `test_evaluation.py` | 6 | The word error rate calculation |
| `test_features.py` | 23 | Transcript, audio, versions, share, actions, reminders, retention |
| `test_generator.py` | 10 | The minutes generator |
| `test_main.py` | 12 | Meetings, upload, status, minutes, export |
| `test_minutes_adapter.py` | 11 | Turning generator output into app minutes |
| `test_minutes_generator.py` | 7 | The minutes generator entry point |
| `test_roles.py` | 12 | Admin, Organizer and Participant access, invited meetings (AMG-F-002) |
| `test_schema.py` | 2 | Output schema |
| `test_security.py` | 29 | Rate limit, encryption, audit log, sanitising, headers |
| `test_transcript.py` | 4 | Transcript data |
| `test_transcription.py` | 11 | Speech-to-text wrapper |
| `test_ui_api.py` | 33 | The routes the web page uses |

## Frontend tests by file

| File | Tests | What it checks |
|---|---|---|
| `src/auth.test.tsx` | 11 | Login page, registration, meeting list |
| `src/features.test.tsx` | 19 | Action tracker, share by email, transcript editor, admin console |
| `src/roles.test.tsx` | 6 | Role-based meeting list, read-only minutes for invited people |
| `src/ui.test.tsx` | 6 | Form validation and attendee rows |
| `src/utils.test.ts` | 12 | Helper functions |

## What these tests do not cover

- Real Whisper accuracy and real model output quality are not unit tested. They are measured in the Transcription Evaluation Report and the System Validation Report.
- The page `App.tsx`, the browser recording step and most of `api.ts` have no unit tests (see the Code Coverage Report). The live browser checks in `docs/auth-validation/`, `docs/requirements-validation/` and `docs/roles-validation/` exercise them.
