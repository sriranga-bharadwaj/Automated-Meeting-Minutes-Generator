# Code Coverage Report

Measured on 20-Nov-2026 while running the full unit test suites (280 tests, all passing; see the Unit Test Report).
Backend: `python -m pytest --cov=app --cov=minutes --cov-branch`. Frontend: `npm run coverage` (Vitest with the v8 provider).
Detailed pages: `docs/coverage/backend-html/index.html` and `docs/coverage/frontend/index.html`. Data: `docs/coverage/backend-coverage.json` and `docs/coverage/frontend/coverage-summary.json`.

## Summary

| Part | Statement (line) coverage |
|---|---|
| Backend (`app/`, `minutes/`) | 90.5% (2132 of 2355 statements) |
| Frontend (`src/`) | 68.9% |

## Backend, per file (statements and missing lines)

Files under 100% only. Eight files have complete coverage and are not listed.

| File | Statements | Missed | Coverage (lines and branches together) |
|---|---|---|---|
| `app/api_v1.py` | 153 | 17 | 87% |
| `app/audio_check.py` | 59 | 14 | 72% |
| `app/auth.py` | 284 | 11 | 94% |
| `app/crypto.py` | 94 | 10 | 86% |
| `app/database.py` | 20 | 6 | 65% |
| `app/export.py` | 85 | 1 | 98% |
| `app/features.py` | 321 | 41 | 85% |
| `app/jobs.py` | 96 | 20 | 77% |
| `app/mailer.py` | 30 | 0 | 95% |
| `app/main.py` | 233 | 24 | 88% |
| `app/minutes_adapter.py` | 71 | 2 | 97% |
| `app/minutes_generator.py` | 37 | 1 | 96% |
| `app/pipeline.py` | 163 | 14 | 90% |
| `app/security.py` | 66 | 0 | 99% |
| `app/sources.py` | 29 | 1 | 93% |
| `app/transcription.py` | 103 | 35 | 66% |
| `app/versions.py` | 16 | 1 | 89% |
| `minutes/generator.py` | 265 | 23 | 89% |
| `minutes/prompts.py` | 10 | 2 | 80% |

The last column is the combined line and branch figure that coverage.py prints. The line-only and branch-only figures are in the Branch Coverage Report and the summary above.

## Frontend, per file

| File | Statements | Branches | Functions |
|---|---|---|---|
| All files | 68.89% | 77.8% | 40.65% |
| `src/App.tsx` | 0% | 0% | 0% |
| `src/api.ts` | 29.6% | 60% | 4.61% |
| `src/utils.ts` | 89.7% | 92.85% | 81.81% |
| `components/ActionTracker.tsx` | 92.18% | 84.37% | 85.71% |
| `components/AdminConsole.tsx` | 97% | 80.48% | 100% |
| `components/AudioStep.tsx` | 68.46% | 45.71% | 35.29% |
| `components/Login.tsx` | 98.33% | 88.23% | 83.33% |
| `components/MeetingForm.tsx` | 98.48% | 86.36% | 81.81% |
| `components/MeetingList.tsx` | 95.65% | 82.6% | 100% |
| `components/MinutesEditor.tsx` | 87.05% | 64.58% | 17.24% |
| `components/Processing.tsx` | 74.24% | 62.5% | 66.66% |
| `components/ShareMinutes.tsx` | 100% | 87.5% | 100% |
| `components/TranscriptPanel.tsx` | 90% | 86.48% | 62.5% |
| `components/VersionHistory.tsx` | 93.61% | 83.33% | 100% |

`types.ts` holds only type definitions and has nothing to execute. Open the HTML report for exact line numbers.

## Where coverage is low, and why

- `app/transcription.py` (66%): the lines that load the real Whisper model and run it are not run by the unit tests, because that needs the model download. They are measured by the Transcription Evaluation Report instead.
- `app/audio_check.py` (72%) and `app/jobs.py` (77%): error paths for corrupt files and failed jobs are only partly tested.
- `app/database.py` (65%): the migration steps for older databases only run on an old database file.
- Frontend `App.tsx` (0%) and most of `api.ts` (29.6%): the page shell and the real HTTP calls have no unit tests. The unit tests replace the API with mocks. The live browser checks (`docs/auth-validation/`, `docs/requirements-validation/`, `docs/roles-validation/`) cover these paths but are not counted here.
- Frontend `AudioStep.tsx` (68%): the browser recording code needs a real microphone.
- The frontend function coverage (40.65%) is low mostly because of `api.ts` and `App.tsx`.

This report states the measured numbers only and does not claim a target was met.
