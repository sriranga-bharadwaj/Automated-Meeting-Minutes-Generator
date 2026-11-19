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

## Login and roles
The web app starts at a login page. The first account created becomes the **administrator**; every
later account is a normal **user**.

- A user sees and opens only their own meetings, and can delete them.
- An administrator sees every meeting (with its owner), the user list, can change roles, delete any
  meeting, and use the **Admin console** (jobs, audit log, reminders, retention).
- Passwords are stored as salted Argon2id hashes. Five wrong passwords lock an account for 15 minutes.
- Access tokens last 30 minutes; the page renews them with a rotating refresh token. Logging out ends the session.
- Tokens are signed with `AMMG_SECRET_KEY`, or with a key created in `backend/.ammg_secret` (not committed).
- Meetings created before login existed are given to the first account created.
- `AUTH_REQUIRED=false` switches the login checks off (the tests use this). The offline demo
  (`VITE_USE_MOCK=true`) has no login.

## Features beyond the basic flow
- **Transcript editor** with the recording: click a segment to hear it, edit the text, type a speaker name.
- **Source links**: "▶ m:ss" next to each topic, decision and action item plays the recording from that moment.
- **Version history**: every save is kept; restore an older version.
- **Share by email** and **deadline reminders** need a mail server: set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`,
  `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_TLS`. To try it without a mail account run
  `python scripts/smtp_sink.py` (saves each mail as a `.eml` file) and start the backend with
  `SMTP_HOST=127.0.0.1 SMTP_PORT=1025 SMTP_TLS=false`.
- **Action tracker**: all action items across meetings, with filters and a Done checkbox.
- **Retention**: set `RETENTION_DAYS=90` to delete older meetings automatically (hourly), or use the Admin console.

## Security settings
- **Encryption at rest**: recordings, transcripts and minutes are encrypted with AES-256-GCM. The key is `AMMG_DATA_KEY`
  (base64 of 32 bytes) or the file `backend/.ammg_datakey`. **Back this key up: without it the data cannot be read.**
  `ENCRYPT_AT_REST=false` stores new data unencrypted.
- **HTTPS**: `python scripts/make_dev_cert.py`, then
  `uvicorn app.main:app --port 8443 --ssl-keyfile dev-key.pem --ssl-certfile dev-cert.pem`. `FORCE_HTTPS=true` redirects HTTP to HTTPS.
  Use a real certificate in production.
- **Rate limits**: 100 requests per minute per user, 10 login attempts per minute per address (`RATE_LIMIT_ENABLED=false` to turn off).
- **Uploads** are checked by content type, file signature and decoding; ClamAV (`clamscan`) is used when installed.
  `AUDIO_PREVALIDATE=false` skips these checks.
- **Audit log**: logins, shares, exports, deletes, role changes and edits are recorded in a hash chain (Admin console).
- See `docs/Requirements_Status.md` for what is and is not done.

## Tests
    cd backend && python -m pytest        # backend (some model tests are skipped unless Ollama is running)
    cd frontend && npm test               # frontend unit tests
