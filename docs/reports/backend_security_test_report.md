# Backend Security Test Report

**Project:** Automated Meeting Minutes Generator (AMMG)  
**Security Evaluator:** Srijan Akshit (Member 1 - Backend)  
**Date:** 2026-11-19  
**Target Application:** AMMG FastAPI Backend (`/api/v1`)  
**Scope:** Application-layer security controls, input validation, file upload defenses, and failure resilience.  

---

## 1. Security Scope Disclosure & Baseline Architecture

> [!IMPORTANT]
> **Explicit Security Architecture Disclosure:**
> The current version of the AMMG application is a functional prototype focused on speech-to-text pipeline execution, meeting minutes generation, and document export. The following enterprise security features are **not currently implemented** within this backend service:
>
> 1. **User Authentication & Login:** There is no user registration, password hashing (Argon2/bcrypt), or credential validation implemented in the backend code.
> 2. **JWT / Token Authorization:** Endpoints do not validate bearer tokens, session signatures, or claims. (The frontend client stores a placeholder token in `sessionStorage` for future integration, but requests are unauthenticated at the backend level).
> 3. **Role-Based Access Control (RBAC):** There are no permission checks distinguishing between Admin, Organizer, or Attendee roles. Any client with network access can create, query, and modify meetings.
> 4. **In-App TLS / HTTPS Termination:** The FastAPI backend runs natively over plain HTTP (default port 8000). TLS termination, HTTPS redirects, and certificate handling must be provided by external reverse proxies (e.g. Nginx, Caddy, Cloudflare, or AWS ALB) in production.
>
> These are acknowledged system limitations scheduled for future development phases. The security testing detailed below concentrates on **application-level input validation, file storage protection, injection defense, and error-handling resilience**.

---

## 2. Security Test Matrix

| Test ID | Security Area | Threat / Misuse Scenario | Test Input / Technique | Expected Behavior | Observed Result | Status | Test Reference |
|---|---|---|---|---|---|---|---|
| **SEC-01** | Upload Protection | **Oversized File Denial of Service:** An attacker uploads a massive audio file to exhaust server disk space or memory. | Streamed payload exceeding `MAX_AUDIO_BYTES` (e.g., > 25 MB / configured limit). | Server terminates upload with HTTP 413 `TOO_LARGE` and deletes all unlinked partial files from disk. | HTTP 413 returned; zero byte residual files remain on disk. | **PASS** | `test_oversized_upload_is_rejected_and_cleaned_up` |
| **SEC-02** | File Validation | **Extension Blacklist Bypass:** Attacker uploads executable or script file (`.exe`, `.py`, `.sh`, `.txt`) to execute arbitrary code. | File named `notes.txt` or `payload.exe` submitted to audio upload endpoint. | Server validates file extension against whitelist `{mp3, wav, m4a, ogg, webm, mp4}`, returning HTTP 415 `UNSUPPORTED`. | Rejected with HTTP 415 and `{"code": "UNSUPPORTED"}`. | **PASS** | `test_upload_errors` |
| **SEC-03** | File Validation & Spoofing | **MIME / Extension Spoofing:** Attacker renames a text, shell script, or binary payload with an allowed audio extension (`payload.wav`). | Plain text and script commands disguised as `.wav` (`"SELECT * FROM users; <script>alert(1)</script>"`). | File passes preliminary extension check but is identified as invalid during audio decoding. Job transitions to `FAILED` with descriptive error; server remains operational without crashing. | HTTP 201 on upload; background transcription identifies invalid audio stream; status reports `FAILED`; backend does not crash. | **PASS** | `test_security_extension_spoofing_handled_by_transcription` |
| **SEC-04** | File Storage Integrity | **Path Traversal via Filename:** Attacker sends directory traversal sequences (`../../etc/passwd` or `..\\..\\payload.wav`) in filename to overwrite sensitive files. | `UploadFile` with `filename="../../../../exploit.wav"`. | Server must not construct disk paths using raw user filename. File must be stored under an isolated UUID in the dedicated uploads directory. | File stored as `<uuid>.wav` inside `uploads/audio/`. Target directory outside uploads remained completely unaffected. | **PASS** | `test_security_path_traversal_filename_neutralized` |
| **SEC-05** | Input Sanitization | **Cross-Site Scripting (XSS) & SQL Injection in Text Fields:** Attacker injects HTML/JS tags or SQL syntax into meeting title or agenda. | Title: `<script>alert('xss')</script>`, Agenda: `'; DROP TABLE meetings; --`. | Data stored as literal parameters using SQLAlchemy ORM parameterization (no SQLi); special characters preserved literally for downstream HTML-escaping. | Accepted and stored safely as literal strings; database schema intact; retrieved without code execution. | **PASS** | `test_security_xss_and_sql_injection_in_meeting_inputs` |
| **SEC-06** | Data Integrity | **Zero-Byte File Upload:** Attacker submits empty file to trigger division-by-zero or decoder crashes. | Audio upload with `data = b""` (0 bytes). | Server rejects empty files with HTTP 400 `EMPTY` and unlinks temporary file. | Rejected with HTTP 400 `EMPTY`; no database record created. | **PASS** | `test_upload_errors` |
| **SEC-07** | Concurrency & Integrity | **Lost Updates / Race Conditions in Minutes Editing:** Two users edit minutes concurrently; User B overwrites User A's changes without seeing them. | User submits `SaveMinutesRequest` containing an outdated `version` number (`version: 999` vs `current: 1`). | Server detects version mismatch and rejects request with HTTP 409 `CONFLICT`. | HTTP 409 returned with message: *"Someone else changed these minutes. Reload to see the latest version."* | **PASS** | `test_saving_minutes_version_conflict_rejection` |
| **SEC-08** | Transaction Safety | **Partial State Injection on Database Failure:** Database or network crashes midway through audio upload. | Database record instantiation throws `RuntimeError` during commit. | Server issues transaction rollback (`db.rollback()`), deletes partial disk files, and prevents orphan database records. | HTTP 500 returned; no orphan records committed in `audio_files` table. | **PASS** | `test_security_database_rollback_on_upload_error` |
| **SEC-09** | Resource Exhaustion | **Speechless Audio Starvation:** Upload of long silent recordings or background noise to stall LLM generation. | WAV file containing no detected speech. | ASR pipeline catches absence of detected speech; aborts LLM invocation; marks job `FAILED` with user-friendly error. | Job marked `FAILED` with *"No speech was detected in the audio."*; LLM not called. | **PASS** | `test_recording_without_speech_fails_politely` |
| **SEC-10** | Document Generation Security | **Export Format Fuzzing:** Client requests unsupported or dangerous export extensions (`.exe`, `.bat`, `.dll`). | POST `/meetings/{id}/export` with `{"format": "exe"}`. | Server validates format against whitelist `("docx", "pdf", "md")`, rejecting invalid formats with HTTP 400. | Rejected with HTTP 400 `INVALID_FORMAT`. | **PASS** | `test_export_invalid_format_rejected` |

---

## 3. Evaluation of Application-Level Security Controls

### 3.1. Path Traversal & Storage Isolation
In `backend/app/api_v1.py`, filenames submitted by users are stripped of relative directory components (`Path(raw_filename).name`), and the storage target on disk is uniquely generated:
```python
audio_id = str(uuid4())
destination = AUDIO_UPLOAD_DIR / f"{audio_id}{extension}"
```
This guarantees that uploaded audio cannot overwrite system binaries, configuration files, or database storage regardless of user-supplied filenames.

### 3.2. SQL Injection Resistance
All database operations utilize SQLAlchemy 2.0 ORM expressions:
```python
meeting = db.query(MeetingDB).filter(MeetingDB.id == meeting_id).first()
```
Inputs are passed as parameterized values directly to SQLite, preventing classic and blind SQL injection vectors.

### 3.3. Memory & Resource Bounds
- Audio uploads are processed using 1 MB chunks with cumulative size checking against `MAX_AUDIO_BYTES`.
- If an upload exceeds the threshold, the file handle is closed, the file is unlinked, and HTTP 413 is returned before the file can consume excessive disk resources.

---

## 4. Recommendations for Future Security Roadmap

1. **Authentication Layer:** Implement OAuth2 / JWT authentication using industry-standard libraries (e.g. `passlib[argon2]`, `pyjwt`).
2. **Access Control / IDOR Defense:** Restrict meeting access to the meeting creator and designated attendees via tenant/user authorization checks.
3. **Infrastructure TLS:** Deploy the backend behind a reverse proxy (e.g. Nginx or Traefik) configured with TLS 1.3, HSTS headers, and automatic HTTP-to-HTTPS redirection.
4. **Rate Limiting:** Implement token-bucket rate limiting (e.g., via `slowapi` or Redis) to protect endpoints from automated scraping or upload flooding.
