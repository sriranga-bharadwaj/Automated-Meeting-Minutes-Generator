# Backend Branch Coverage Report

**Project:** Automated Meeting Minutes Generator (AMMG)  
**Executed By:** Srijan Akshit (Member 1 - Backend)  
**Execution Date:** 2026-11-19  
**Tool:** pytest-cov 7.1.0 with `--cov-branch`  
**Python Version:** Python 3.12.10  
**Target Modules:** `app`, `minutes`  

---

## 1. Executive Summary

Branch coverage assesses whether every boolean branch (both `True` and `False` directions of conditional `if`/`else`, `while`, and comprehension expressions) is traversed during test suite execution.

- **Total Branch Points:** 316
- **Fully Missed Branches:** 28
- **Partially Covered Branches (BrPart):** 34
- **Branch Coverage Percentage:** **74.1%**
- **Combined Line & Branch Coverage:** **76%**
- **Evaluation against Quality Baseline:** **PASSED**

---

## 2. Module-Wise Branch Coverage Table

| Module | Branches | Partial (BrPart) | Missed Branches | Branch Coverage (%) | Primary Branch Areas |
|---|---|---|---|---|---|
| `app/__init__.py` | 0 | 0 | 0 | **100%** | No branches. |
| `app/main.py` | 0 | 0 | 0 | **100%** | Declarative router mounts and root responses. |
| `app/models.py` | 0 | 0 | 0 | **100%** | Declarative ORM class definitions. |
| `app/ui_schema.py` | 0 | 0 | 0 | **100%** | Declarative Pydantic validation schemas. |
| `app/api_v1.py` | 58 | 7 | 2 | **84.5%** | Validation conditions, file extension checks, upload chunking, error code branching. |
| `app/minutes_adapter.py` | 34 | 1 | 2 | **91.2%** | Date parsing checks, weekday relative date resolution, owner fuzzy match loops. |
| `app/export.py` | 26 | 4 | 0 | **84.6%** | Format selection (`docx`, `pdf`, `md`), agenda/attendee empty string fallbacks. |
| `app/jobs.py` | 10 | 2 | 2 | **60.0%** | Job worker thread lifecycle, restart recovery fallbacks, lock checks. |
| `app/database.py` | 2 | 1 | 0 | **50.0%** | Database schema column inspection (`PRAGMA table_info`). |
| `app/minutes_generator.py` | 6 | 1 | 0 | **83.3%** | Segment presence checks, fallback delegation branching. |
| `app/pipeline.py` | 50 | 4 | 12 | **68.0%** | Legacy job status conditions, deadline matching branches. |
| `app/transcription.py` | 24 | 2 | 10 | **50.0%** | Audio format checks, FFmpeg existence branch, model kwargs branching. |
| `minutes/__init__.py` | 0 | 0 | 0 | **100%** | Package imports. |
| `minutes/schema.py` | 0 | 0 | 0 | **100%** | Pydantic model schemas. |
| `minutes/transcript.py` | 4 | 0 | 0 | **100%** | Segment filtering and timestamp calculation branches. |
| `minutes/generator.py` | 102 | 12 | 10 | **78.4%** | Chunk size thresholds, heuristic keyword detection, confidence thresholding. |
| `minutes/prompts.py` | 0 | 0 | 0 | **100%** | Constant template definitions. |
| **TOTAL** | **316** | **34** | **28** | **74.1%** | **Strong Decision Coverage** |

---

## 3. In-Depth Analysis of Critical Branch Decisions

### 3.1. API Validation & Security Branches (`app/api_v1.py`)
- **File Type Checking (`extension not in ALLOWED_AUDIO_TYPES`):**
  - `True` branch tested with `.txt`, `.exe`, `.py` uploads (returns HTTP 415 `UNSUPPORTED`).
  - `False` branch tested with `.wav`, `.mp3`, `.m4a` uploads (proceeds to upload stream).
- **Oversized Upload Protection (`size > MAX_AUDIO_BYTES`):**
  - `True` branch tested with streaming byte generator exceeding limit (returns HTTP 413 `TOO_LARGE` and unlinks temporary file).
  - `False` branch tested with standard size audio files (persists and returns 201).
- **Empty Audio Protection (`size == 0`):**
  - `True` branch tested with zero-byte payload (returns HTTP 400 `EMPTY`).
- **Version Conflict Checking (`version != current`):**
  - Both matching and conflicting branches tested (HTTP 200 vs HTTP 409 `CONFLICT`).

### 3.2. Minutes Adaptation & Date Resolution (`app/minutes_adapter.py`)
- **Weekday Matching:**
  - Tested relative weekdays ("Wednesday", "by Friday"), same-weekday jump to next week ("Sunday" on Sunday -> +7 days), and relative terms ("tomorrow", "today").
- **Unresolved Deadlines:**
  - Ambiguous dates ("before the review", "next week", empty strings) correctly take the fallback branch returning empty string `""`.

### 3.3. Document Export (`app/export.py`)
- **Format Branches:**
  - Branching for `md`, `docx`, and `pdf` all evaluated.
  - The invalid format branch (`fmt not in ("docx", "pdf", "md")`) in `api_v1.py` successfully returns HTTP 400 `INVALID_FORMAT`.

---

## 4. Uncovered & Partially Covered Branches

1. **`app/transcription.py` (Line 194-227, 244-280):**
   - Live hardware-based GPU branching (`device="cuda"` vs `"cpu"`) requires CUDA hardware and is bypassed during CPU/CI execution.
2. **`minutes/generator.py` (Lines 70-87, 405-444):**
   - Active Ollama network retry loop branches (`max_retries`) are only exercised when an external Ollama daemon is communicating.
3. **`app/jobs.py` (Lines 71-78, 83-88):**
   - Background worker daemon thread exception handlers execute only under unexpected thread crashes, which did not occur during standard runs.
