# Backend Unit Test Execution Report

**Project:** Automated Meeting Minutes Generator (AMMG)  
**Executed By:** Srijan Akshit (Member 1 - Backend)  
**Execution Date:** 2026-11-19  
**Platform:** Windows 11 (AMD64)  
**Python Version:** Python 3.12.10  
**Pytest Version:** pytest 9.1.1 (pluggy 1.7.0)  
**Plugins:** anyio 4.15.1, pytest-cov 7.1.0  

---

## 1. Execution Summary

```text
============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.1.1, pluggy-1.7.0
rootdir: C:\Users\Srijan\Automated-Meeting-Minutes-Generator\backend
plugins: anyio-4.15.1, cov-7.1.0
collected 129 items

tests\test_api_v1.py ..................................                  [ 26%]
tests\test_chunking.py ...............................                   [ 50%]
tests\test_generator.py ssssssssss                                       [ 58%]
tests\test_main.py ....                                                  [ 61%]
tests\test_minutes_adapter.py ...........                                [ 69%]
tests\test_minutes_generator.py .....                                    [ 73%]
tests\test_schema.py ....                                                [ 76%]
tests\test_transcript.py ....                                            [ 79%]
tests\test_transcription.py .....ssss                                    [ 86%]
tests\test_ui_api.py .................                                   [100%]

======================= 115 passed, 14 skipped in 8.83s =======================
```

- **Total Tests Collected:** 129
- **Passed:** 115 (100% of executed tests)
- **Failed:** 0
- **Errors:** 0
- **Skipped:** 14 (conditioned on hardware/external dependencies)
- **Execution Time:** 8.83 seconds

---

## 2. Command Executed

```bash
cd backend
python -m pytest --cov=app --cov=minutes --cov-branch --cov-report=term-missing --cov-report=xml
```

---

## 3. Test Suite Breakdown by Module

| Test Module | Tests Collected | Passed | Skipped | Failed | Focus Area |
|---|---|---|---|---|---|
| `tests/test_api_v1.py` | 34 | 34 | 0 | 0 | Consolidated `/api/v1` routes: meeting CRUD, audio uploads, job status, minutes versioning, export formats, security test cases. |
| `tests/test_chunking.py` | 31 | 31 | 0 | 0 | Transcript chunking, token boundary management, and action-item/decision sentence parsing. |
| `tests/test_generator.py` | 10 | 0 | 10 | 0 | Ollama local model end-to-end integration tests (skipped when `qwen2.5:7b` model is not pulled). |
| `tests/test_main.py` | 4 | 4 | 0 | 0 | Root endpoint (`/`), health endpoint (`/health`), legacy route retirement checks, and CORS configuration. |
| `tests/test_minutes_adapter.py` | 11 | 11 | 0 | 0 | UI format adaptation, deadline resolution (relative dates, weekdays), and canonical attendee matching. |
| `tests/test_minutes_generator.py` | 5 | 5 | 0 | 0 | Fallback heuristic generator and keyword-based action/decision extraction. |
| `tests/test_schema.py` | 4 | 4 | 0 | 0 | Pydantic model validations for domain minutes, action items, UI schemas, and database session generator. |
| `tests/test_transcript.py` | 4 | 4 | 0 | 0 | Timestamp formatting (`HH:MM:SS`), segment sorting, and transcript text compilation. |
| `tests/test_transcription.py` | 9 | 5 | 4 | 0 | Audio validation, missing file errors, WhisperModel mocking, and FFmpeg preprocessing checks (4 live FFmpeg tests skipped on environments without FFmpeg binary). |
| `tests/test_ui_api.py` | 17 | 17 | 0 | 0 | Pipeline state management, fallback job status checks, result persistence, and deadline resolution. |
| **Total** | **129** | **115** | **14** | **0** | **100% Pass Rate for Active Tests** |

---

## 4. Analysis of Skipped Tests

1. **`tests/test_generator.py` (10 tests skipped):**
   - **Reason:** Requires a running local Ollama instance with model `qwen2.5:7b` pulled.
   - **Condition:** `@pytest.mark.skipif(not ollama_available(), reason="Ollama or qwen2.5:7b model is not available")`.
   - **Design Intention:** AMMG supports a keyword-based fallback engine when Ollama is unavailable; unit test suites are kept independent of heavy GPU/external LLM services.
2. **`tests/test_transcription.py` (4 tests skipped):**
   - **Reason:** FFmpeg binary was not detected on the local development machine's `PATH`.
   - **Condition:** `@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="FFmpeg is not installed")`.
   - **CI Environment:** In GitHub Actions CI (`.github/workflows/backend-ci.yml`), `ffmpeg` is installed via `sudo apt-get install -y ffmpeg`, ensuring these tests execute in automated CI pipelines.

---

## 5. Known Limitations & Untested Areas

1. **Live Whisper Model Weight Loading:**
   - Whisper weights (~150 MB - 1.5 GB) are not downloaded during automated test execution. All transcription tests use deterministic mocks (`FakeModel`) to prevent CI timeouts, bandwidth spikes, and non-deterministic hardware issues.
2. **User Authentication & Session Controls:**
   - As documented in the Security Scope Disclosure, user login, JWT authentication, and RBAC are not yet implemented in the application layer. Tests verify application behavior under this design premise.
