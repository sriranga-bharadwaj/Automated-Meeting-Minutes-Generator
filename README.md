# Automated Meeting Minutes Generator (AMMG)

Upload or record a meeting, and get editable, structured minutes: summary, key discussions,
decisions, and action items with owners and deadlines. Export them as Word, PDF or Markdown.

| Part | Where | What it does |
|---|---|---|
| Backend and Consolidated API | `backend/app/main.py`, `api_v1.py`, `database.py`, `models.py` | FastAPI application, consolidated `/api/v1` routes, audio upload, SQLite database |
| Audio and transcription | `backend/app/transcription.py` | FFmpeg preprocessing, faster-whisper speech-to-text with timestamps |
| Minutes generator | `backend/minutes/`, `backend/app/minutes_generator.py` | Turns the transcript into structured minutes (local Ollama model, keyword fallback) |
| Frontend | `frontend/` | React + TypeScript web app (Vite dev server proxies `/api/v1` directly to backend) |
| Pipeline & Utilities | `backend/app/jobs.py`, `export.py`, `ui_schema.py` | Asynchronous job execution, progress status, DOCX/PDF/Markdown export |

## What you need installed
- Python 3.10+ (Python 3.12 recommended)
- [FFmpeg](https://ffmpeg.org/download.html) on your PATH (`ffmpeg -version` must work)
- Node.js 18+
- Optional: [Ollama](https://ollama.com) with `ollama pull qwen2.5:7b` for AI-written minutes.
  Without it the app still works and uses a simpler keyword-based draft (items are flagged for review).

## Run it
Terminal 1 (Backend):

    cd backend
    pip install -r ../requirements.txt
    uvicorn app.main:app --port 8000

Terminal 2 (Frontend):

    cd frontend
    npm install
    npm run dev

Open http://localhost:5173. The first transcription downloads the Whisper model (about 150 MB).
Set `WHISPER_MODEL_SIZE=small` for better accuracy on slower, longer meetings.

If you pulled an older version and see database errors, delete `backend/ammg.db` and start again.

## API Architecture & Flow (/api/v1)

The backend API is consolidated under the `/api/v1` base path (see [API Consolidation Report](docs/API_CONSOLIDATION.md)):

1. The web form creates a meeting: `POST /api/v1/meetings`.
2. Audio is uploaded: `POST /api/v1/meetings/{id}/audio` (starts background job automatically).
3. The UI can also trigger or verify processing: `POST /api/v1/meetings/{id}/process`.
4. The UI polls job progress: `GET /api/v1/meetings/{id}/status` (`QUEUED`, `TRANSCRIBING`, `ANALYSING`, `READY` or `FAILED`). If failed, `POST /api/v1/meetings/{id}/retry` restarts the job.
5. The user reads and edits minutes: `GET` and `PUT /api/v1/meetings/{id}/minutes` (optimistic locking prevents lost updates via HTTP 409 conflict checks).
6. The user exports minutes: `POST /api/v1/meetings/{id}/export` (supports `docx`, `pdf`, `md`).

Interactive OpenAPI documentation is available at http://localhost:8000/docs. Root status probes are available at `GET /` and `GET /health`.

## Testing & Quality Assurance

### Running Backend Tests
Execute the backend test suite from the `backend/` directory:

    cd backend
    python -m pytest

Some model tests in `test_generator.py` are automatically skipped unless Ollama with `qwen2.5:7b` is running; hardware-dependent FFmpeg tests skip if FFmpeg is not detected on PATH.

### Generating Code & Branch Coverage
Run pytest with `pytest-cov` to generate human-readable terminal output and a machine-readable XML report:

    cd backend
    python -m pytest --cov=app --cov=minutes --cov-branch --cov-report=term-missing --cov-report=xml:coverage.xml

Current test execution metrics:
- **Test suite:** 115 passed, 14 skipped, 0 failed.
- **Line & Branch coverage:** **76%** (exceeds the 70% requirement from STP AMG-NF-007).
- Detailed test and security reports are saved in `docs/reports/`.

### Continuous Integration (GitHub Actions)
The backend CI workflow is defined in `.github/workflows/backend-ci.yml`. It:
- Automatically triggers on every push to all branches and pull requests targeting `main`.
- Runs on `ubuntu-latest` with Python 3.12 and cached pip dependencies.
- Installs `ffmpeg` and backend requirements deterministically.
- Executes the full test suite with branch coverage enforcement (`--cov-fail-under=70`).
- Uploads the generated `coverage.xml` report as an artifact.
