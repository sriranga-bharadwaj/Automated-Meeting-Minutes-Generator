# Backend Code Coverage Report

**Project:** Automated Meeting Minutes Generator (AMMG)  
**Executed By:** Srijan Akshit (Member 1 - Backend)  
**Date of Execution:** 2026-11-19  
**Tool:** pytest-cov 7.1.0 / Coverage.py 7.17.3  
**Python Version:** Python 3.12.10  
**Target Modules:** `app`, `minutes`  

---

## 1. Executive Summary

- **Total Statements:** 1,137
- **Missed Statements:** 244
- **Total Covered Statements:** 893
- **Total Line Coverage:** **78.5%** (Combined Line + Branch: **76%**)
- **Target Threshold (STP AMG-NF-007):** ≥ 70%
- **Result:** **PASSED** (Exceeds requirement by 6%)

---

## 2. Execution Command

```bash
cd backend
python -m pytest --cov=app --cov=minutes --cov-branch --cov-report=term-missing --cov-report=xml:coverage.xml
```

---

## 3. Module-Wise Statement Coverage Breakdown

| Module | Statements | Miss | Statement Coverage (%) | Status / Comments |
|---|---|---|---|---|
| `app/__init__.py` | 0 | 0 | **100%** | Package initializer. |
| `app/main.py` | 21 | 0 | **100%** | Root endpoints (`/`, `/health`), CORS, middleware, router mount. |
| `app/models.py` | 40 | 0 | **100%** | SQLAlchemy ORM models (`MeetingDB`, `AudioDB`, `MinutesDB`, `TranscriptDB`, `MeetingMetaDB`). |
| `app/ui_schema.py` | 34 | 0 | **100%** | Pydantic data schemas for UI serialization. |
| `app/minutes_adapter.py` | 71 | 2 | **97%** | Adaptation of raw LLM output into UI minutes, owner guessing, deadline parser. |
| `app/api_v1.py` | 186 | 5 | **97%** | Consolidated API endpoints, request validation, upload handler, export renderer. |
| `app/export.py` | 85 | 1 | **99%** | Multi-format rendering engine (Markdown, DOCX, PDF). |
| `app/minutes_generator.py` | 33 | 1 | **97%** | Adapter delegating to NLP minutes generation engine. |
| `app/database.py` | 16 | 1 | **94%** | Database connection pooling, session generator, schema migrations. |
| `app/jobs.py` | 96 | 20 | **79%** | Background processing thread pool, in-memory state tracking, job execution. |
| `app/pipeline.py` | 163 | 78 | **52%** | Legacy pipeline utilities (superseded by `app/jobs.py`). |
| `app/transcription.py` | 95 | 57 | **40%** | Faster-Whisper wrapper and FFmpeg audio preprocessing (untested branches require live FFmpeg/GPU). |
| `minutes/__init__.py` | 3 | 0 | **100%** | Minutes package entry point. |
| `minutes/schema.py` | 20 | 0 | **100%** | Pydantic data validation schemas for meeting minutes. |
| `minutes/transcript.py` | 14 | 0 | **100%** | Segment timestamp formatting and transcript generation. |
| `minutes/generator.py` | 250 | 75 | **70%** | Chunking, heuristic fallback, action item extraction, Ollama integration. |
| `minutes/prompts.py` | 10 | 4 | **60%** | Prompt building templates for Ollama models. |
| **TOTAL** | **1,137** | **244** | **78.5%** | **Complies with STP AMG-NF-007 (≥ 70%)** |

---

## 4. Coverage Analysis by Subsystem

### 4.1. Core API & Web Services (97% - 100%)
- The consolidated `/api/v1` routes (`app/api_v1.py` and `app/main.py`) achieved exceptional coverage (**97%–100%**).
- All edge cases including missing entities, malformed payloads, file extension validation, oversized uploads, version conflict handling (HTTP 409), and multi-format document generation were executed and verified.

### 4.2. Document Export Engine (99%)
- `app/export.py` renders markdown, DOCX documents via `python-docx`, and PDF streams via `reportlab`. All three export paths are systematically exercised with complete assertion on output headers and byte signatures.

### 4.3. Domain & Data Modeling (100%)
- All SQLAlchemy database models and Pydantic validation schemas achieved 100% statement coverage.

### 4.4. Speech-to-Text & Transcription (40%)
- `app/transcription.py` statements missed correspond to:
  - Hardware-dependent GPU execution branches.
  - Live FFmpeg audio conversion execution (skipped locally when FFmpeg is not in `PATH`, but executed in CI).
  - Live faster-whisper model weight downloads (mocked in test suite).

---

## 5. Artifact Reference

The machine-readable Cobertura XML coverage report is stored in the repository at:
`docs/reports/coverage.xml`
