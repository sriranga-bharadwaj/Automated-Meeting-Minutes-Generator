# Branch Coverage Report

Measured on 20-Nov-2026 with the same runs as the Code Coverage Report (backend `pytest --cov-branch`, frontend Vitest v8). All 280 tests passed.
Detailed pages: `docs/coverage/backend-html/index.html` (shows partly covered branches) and `docs/coverage/frontend/index.html`.

## Summary

| Part | Branches | Covered | Branch coverage |
|---|---|---|---|
| Backend (`app/`, `minutes/`) | 648 | 531 | 81.9% (81 branches partly covered) |
| Frontend (`src/`) | 410 | 319 | 77.8% |

For the backend, line coverage is 90.5% and combined line and branch coverage is 88.7%.

## Backend branches, per file

Partly covered branches ("BrPart") out of all branches, for files with any gap. These are from the coverage.py table.

| File | Branches | Partly covered |
|---|---|---|
| `app/api_v1.py` | 42 | 3 |
| `app/audio_check.py` | 26 | 4 |
| `app/auth.py` | 88 | 8 |
| `app/crypto.py` | 20 | 4 |
| `app/database.py` | 6 | 3 |
| `app/export.py` | 26 | 1 |
| `app/features.py` | 96 | 18 |
| `app/jobs.py` | 10 | 2 |
| `app/mailer.py` | 8 | 2 |
| `app/main.py` | 42 | 6 |
| `app/minutes_adapter.py` | 34 | 1 |
| `app/minutes_generator.py` | 10 | 1 |
| `app/pipeline.py` | 50 | 7 |
| `app/security.py` | 18 | 1 |
| `app/sources.py` | 12 | 2 |
| `app/transcription.py` | 26 | 3 |
| `app/versions.py` | 2 | 1 |
| `minutes/generator.py` | 110 | 14 |

## Frontend branches, per file

| File | Branch coverage |
|---|---|
| All files | 77.8% |
| `src/App.tsx` | 0% |
| `src/api.ts` | 60% |
| `src/utils.ts` | 92.85% |
| `components/ActionTracker.tsx` | 84.37% |
| `components/AdminConsole.tsx` | 80.48% |
| `components/AudioStep.tsx` | 45.71% |
| `components/Login.tsx` | 88.23% |
| `components/MeetingForm.tsx` | 86.36% |
| `components/MeetingList.tsx` | 82.6% |
| `components/MinutesEditor.tsx` | 64.58% |
| `components/Processing.tsx` | 62.5% |
| `components/ShareMinutes.tsx` | 87.5% |
| `components/TranscriptPanel.tsx` | 86.48% |
| `components/VersionHistory.tsx` | 83.33% |

## Notes

- The weakest backend branches are in `app/features.py` (18 partly covered of 96), `app/auth.py` (8 of 88) and `minutes/generator.py` (14 of 110): mostly error and fallback paths such as a missing file, a bad token form or an unavailable model.
- The weakest frontend branches are `AudioStep.tsx` (browser recording), `Processing.tsx` (failure and retry display) and `MinutesEditor.tsx` (45.71%, 62.5% and 64.58%). `App.tsx` is not unit tested.
- This report states the measured numbers only and does not claim a target was met.
