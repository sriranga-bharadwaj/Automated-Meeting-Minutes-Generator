# AMMG Frontend (React + TypeScript + Vite)

Flow: Create meeting -> Upload or record audio -> Processing status -> Edit minutes -> Export.

## Run with the real backend (default)
Terminal 1 (from `backend/`; needs FFmpeg installed, see the main README):

    pip install -r ../requirements.txt
    uvicorn app.main:app --port 8000

Terminal 2 (from `frontend/`):

    npm install
    npm run dev          # http://localhost:5173

Vite forwards `/api/v1/...` to `http://localhost:8000/...`.

## Offline demo (no backend)
    cp .env.example .env     # then set VITE_USE_MOCK=true
    npm run dev

Tip: in demo mode, upload a file with "fail" in its name (e.g. fail.mp3) to see the error and Retry path.

## Endpoints the UI calls
| Call | Purpose |
|---|---|
| `POST /meetings` | create a meeting (title, datetime, agenda, language, attendees) |
| `POST /meetings/{id}/audio` | upload the recording (max 25 MB) |
| `POST /meetings/{id}/process` | start transcription + minutes in the background (called right after upload) |
| `GET /meetings/{id}/status` | poll progress: QUEUED, TRANSCRIBING, ANALYSING, READY, FAILED |
| `POST /meetings/{id}/retry` | run processing again after a failure |
| `GET /meetings/{id}/minutes` | fetch the minutes |
| `PUT /meetings/{id}/minutes` | save edits (409 if someone else saved first) |
| `POST /meetings/{id}/export` | download as `docx`, `pdf` or `md` |

## Tests and reports
    npm test             # unit tests
    npm run coverage     # statements, branches, lines (HTML in coverage/)
    npm run build
