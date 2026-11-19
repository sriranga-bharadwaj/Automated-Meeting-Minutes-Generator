# API Consolidation Report

**Project:** Automated Meeting Minutes Generator (AMMG)  
**Author:** Srijan Akshit (Member 1 - Backend)  
**Date:** 2026-11-19  
**Status:** Approved & Implemented  
**Agreed Interface Contract:** `/api/v1`  

---

## 1. Executive Summary & Context

During development and feature integration across Member 1, Member 3, and Member 4, duplicate and overlapping API routes emerged in the backend:
1. **Unprefixed legacy routes** in `backend/app/main.py` (`/meetings`, `/meetings/{meeting_id}`, `/meetings/{meeting_id}/audio`, `/meetings/{meeting_id}/transcribe`, `/meetings/{meeting_id}/process`, etc.).
2. **Standardized `/api/v1` routes** in `backend/app/api_v1.py` aligned with the asynchronous job model and frontend requirements.

Following alignment discussions among team members (specifically the proposal from Member 4, Swasthik) and an audit of the frontend consumers (`frontend/src/api.ts`, `frontend/vite.config.ts`), the team decided to **consolidate the API under the `/api/v1` prefix** and remove redundant unprefixed meeting endpoints from `main.py`.

---

## 2. Rationales for Consolidating to `/api/v1`

1. **Frontend Integration Alignment:**
   - The React frontend client (`frontend/src/api.ts`) explicitly configures `const BASE = import.meta.env.VITE_API_URL ?? '/api/v1'`.
   - Every API client call (`real.createMeeting`, `real.uploadAudio`, `real.getStatus`, `real.retry`, `real.getMinutes`, `real.saveMinutes`, `real.exportMinutes`) targets `/api/v1`.
2. **Asynchronous Job Lifecycle:**
   - The legacy `/meetings/{meeting_id}/transcribe` endpoint was synchronous, blocking the HTTP connection for multiple minutes while Whisper ran speech recognition and the LLM generated minutes. This led to connection timeouts and browser freezes on realistic audio files.
   - The `/api/v1` architecture uses asynchronous queue-backed processing (`app/jobs.py` and `/status` polling from `QUEUED` to `TRANSCRIBING` to `ANALYSING` to `READY`/`FAILED`), which is required for multi-minute meeting audio.
3. **Clean Versioning & OpenAPI Contract:**
   - Prefixing API routes under `/api/v1` ensures proper API versioning without namespace pollution on the root domain.
   - The root endpoints (`/` and `/health`) remain clean and independent of business resource models.

---

## 3. Route Mapping & Consolidation Decision Matrix

| Original Unprefixed Route | Action | Consolidated Route | Consumers | Justification |
|---|---|---|---|---|
| `GET /` | **PRESERVED** | `GET /` | Health monitors, root probes | Root service info & API discovery; not a duplicate. |
| `GET /health` | **PRESERVED** | `GET /health` | Container orchestration, CI/CD | Standard health check endpoint; returns `{"status": "ok"}`. |
| `POST /meetings` | **REMOVED** | `POST /api/v1/meetings` | `frontend/src/api.ts` (`createMeeting`) | Replaced by versioned endpoint accepting agenda, datetime, language, and attendees. |
| `GET /meetings` | **CONSOLIDATED** | `GET /api/v1/meetings` | Admin / Meeting Listing | Moved under `/api/v1/meetings` with chronological sorting. |
| `GET /meetings/{meeting_id}` | **CONSOLIDATED** | `GET /api/v1/meetings/{meeting_id}` | Direct retrieval | Moved under `/api/v1/meetings/{meeting_id}` with 404 handling. |
| `POST /meetings/{meeting_id}/audio` | **REMOVED** | `POST /api/v1/meetings/{meeting_id}/audio` | `frontend/src/api.ts` (`uploadAudio`) | Replaced by `/api/v1` upload with extension validation, size checking, and automatic background submission. |
| `POST /meetings/{meeting_id}/transcribe` | **REMOVED** | *None (Superseded)* | Legacy manual scripts | Deprecated synchronous endpoint that blocks on model inference; replaced by async status flow. |
| `POST /meetings/{meeting_id}/process` | **CONSOLIDATED** | `POST /api/v1/meetings/{meeting_id}/process` | `frontend/src/api.ts` (`uploadAudio` callback) | Trigger background pipeline/job execution, returns HTTP 202. |
| `GET /meetings/{meeting_id}/status` | **CONSOLIDATED** | `GET /api/v1/meetings/{meeting_id}/status` | `frontend/src/api.ts` (`getStatus`) | Returns job progress (0–100%), stage message, and error details. |
| `POST /meetings/{meeting_id}/retry` | **CONSOLIDATED** | `POST /api/v1/meetings/{meeting_id}/retry` | `frontend/src/api.ts` (`retry`) | Re-submits failed or interrupted processing jobs. |
| `GET /meetings/{meeting_id}/minutes` | **CONSOLIDATED** | `GET /api/v1/meetings/{meeting_id}/minutes` | `frontend/src/api.ts` (`getMinutes`) | Retrieves formatted meeting minutes for the editor. |
| `PUT /meetings/{meeting_id}/minutes` | **CONSOLIDATED** | `PUT /api/v1/meetings/{meeting_id}/minutes` & `PUT /api/v1/minutes/{id}` | `frontend/src/api.ts` (`saveMinutes`) | Persists edited minutes with version increment and 409 conflict detection. |
| `POST /meetings/{meeting_id}/export` | **CONSOLIDATED** | `POST /api/v1/meetings/{meeting_id}/export` | `frontend/src/api.ts` (`exportMinutes`) | Renders minutes into DOCX, PDF, or Markdown files. |

---

## 4. Affected Files & Compatibility Updates

1. **`backend/app/main.py`**:
   - Removed duplicate unprefixed meeting handlers.
   - Retained `GET /`, `GET /health`, CORS middleware, database initialization, and router registration `app.include_router(api_v1_router)`.
2. **`backend/app/api_v1.py`**:
   - Added `GET /meetings` and `GET /meetings/{meeting_id}`.
   - Added `POST /meetings/{meeting_id}/process`.
   - Added `PUT /meetings/{meeting_id}/minutes` in addition to legacy `PUT /minutes/{meeting_id}`.
   - Added `POST /meetings/{meeting_id}/export` supporting DOCX, PDF, and Markdown.
   - Enhanced `create_meeting` response to return both `{"meetingId": ...}` and `{"id": ...}` for dual compatibility with frontend and test suites.
   - Implemented strict path traversal defense during audio file storage (using isolated random UUID filenames).
3. **`frontend/vite.config.ts`**:
   - Removed path rewriting that previously stripped `/api/v1`.
   - Proxy configuration now passes `/api/v1` directly to backend `http://localhost:8000/api/v1`.
4. **Backend Test Suites**:
   - Updated `backend/tests/test_main.py` to verify root endpoints and confirm 404 retirement of legacy unprefixed paths.
   - Expanded `backend/tests/test_api_v1.py` to 34 comprehensive tests covering meeting lifecycle, validation, audio uploads, job processing, minutes editing, version conflicts, export, and security scenarios.
   - Updated `backend/tests/test_ui_api.py` to focus on pipeline functions.

---

## 5. Verification Results

- All 115 unit/integration tests pass cleanly.
- Vite dev server correctly communicates with the `/api/v1` backend endpoints.
- OpenAPI specification documentation at `/docs` reflects the consolidated API structure.
