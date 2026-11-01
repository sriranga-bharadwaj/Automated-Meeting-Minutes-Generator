# Automated Meeting Minutes Generator (AMMG)

Upload or record a meeting, and get editable, structured minutes: summary, key discussions,
decisions, and action items with owners and deadlines. Export them as Word, PDF or Markdown.

| Part | Where | What it does |
|---|---|---|
| Backend and API | `backend/app/main.py`, `database.py`, `models.py` | FastAPI app, meetings, audio upload, database |
| Audio and transcription | `backend/app/transcription.py` | FFmpeg preprocessing, faster-whisper speech-to-text with timestamps |
| Minutes generator | `backend/minutes/`, `backend/app/minutes_generator.py` | Turns the transcript into structured minutes (local Ollama model, keyword fallback) |
| Frontend | `frontend/` | React + TypeScript web app |
| Glue | `backend/app/pipeline.py`, `export.py`, `ui_schema.py` | Background processing, status, minutes for the UI, DOCX/PDF/Markdown export |

## What you need installed
- Python 3.10+
- [FFmpeg](https://ffmpeg.org/download.html) on your PATH (`ffmpeg -version` must work)
- Node.js 18+
- Optional: [Ollama](https://ollama.com) with `ollama pull qwen2.5:7b` for AI-written minutes.
  Without it the app still works and uses a simpler keyword-based draft (items are flagged for review).

## Run it
Terminal 1:

    cd backend
    pip install -r ../requirements.txt
    uvicorn app.main:app --port 8000

Terminal 2:

    cd frontend
    npm install
    npm run dev

Open http://localhost:5173. The first transcription downloads the Whisper model (about 150 MB).
Set `WHISPER_MODEL_SIZE=small` for better accuracy on slower, longer meetings.

If you pulled an older version and see database errors, delete `backend/ammg.db` and start again.

## How a meeting flows through the system
1. The web form creates a meeting (`POST /meetings`) and uploads the audio (`POST /meetings/{id}/audio`, max 25 MB).
2. The UI starts processing (`POST /meetings/{id}/process`). It runs in the background: FFmpeg converts the audio,
   Whisper transcribes it, then the minutes generator writes the minutes.
3. The UI polls `GET /meetings/{id}/status` (QUEUED, TRANSCRIBING, ANALYSING, READY or FAILED).
4. The user edits the minutes (`GET`/`PUT /meetings/{id}/minutes`, autosaved) and exports them (`POST /meetings/{id}/export`).

`POST /meetings/{id}/transcribe` is the older all-in-one endpoint that waits for the result. It is kept for scripts and tests.
Interactive API docs are at http://localhost:8000/docs.

## Tests
    cd backend && python -m pytest        # backend (some model tests are skipped unless Ollama is running)
    cd frontend && npm test               # frontend unit tests
