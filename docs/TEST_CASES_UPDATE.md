# Software Test Plan (STP) - Test Cases & Traceability Update

**Project:** Automated Meeting Minutes Generator (AMMG)  
**Author:** Srijan Akshit (Member 1 - Backend)  
**Date:** 2026-11-19  
**Source Document:** `STP_AMMG_.docx` (Appendix A, Table 6)  
**SRS Reference Document:** `SRS_AMMG (1).docx`  

---

## 1. Summary of Updates

The existing Software Test Plan (`STP_AMMG_.docx`) contains 47 baseline test cases mapped to functional requirements (`AMG-F-xxx`), non-functional requirements (`AMG-NF-xxx`), and security requirements (`AMG-SR-xxx`).

To cover the consolidated `/api/v1` backend integration, concurrent editing conflict defense, and file-upload security scenarios, 6 new test cases have been added to Table 6 of `STP_AMMG_.docx`.

---

## 2. Added Test Cases and SRS Traceability

| TC ID | SRS Req(s) | Level | Scenario / Steps | Expected Result | Automated Test Reference |
|---|---|---|---|---|---|
| **TC-Aud-05** | `AMG-F-011`, `AMG-SR-006` | Integration | Upload audio with path traversal filename (`../../../exploit.wav`). | Filename is sanitized; file is safely isolated under a random UUID in `uploads/audio/`; no write occurs outside upload directory. | `tests/test_api_v1.py::test_security_path_traversal_filename_neutralized` |
| **TC-Aud-06** | `AMG-F-011`, `AMG-SR-006` | Integration | Upload non-audio/script payload renamed with audio extension (`malicious.wav`). | Upload passes file extension check; decoding failure is caught safely during transcription; job transitions to `FAILED` with descriptive error; server remains operational without crashing. | `tests/test_api_v1.py::test_security_extension_spoofing_handled_by_transcription` |
| **TC-Min-07** | `AMG-F-043` | Integration | Save minutes with mismatched/outdated version number (`PUT /api/v1/meetings/{id}/minutes`). | Server returns HTTP 409 Conflict with reload prompt; prevents concurrent lost updates. | `tests/test_api_v1.py::test_saving_minutes_version_conflict_rejection` |
| **TC-Min-08** | `AMG-F-044` | Integration | Request minutes export with invalid/unsupported format (`POST /api/v1/meetings/{id}/export` with `format: "exe"`). | Server rejects request with HTTP 400 `INVALID_FORMAT`; only `docx`, `pdf`, and `md` allowed. | `tests/test_api_v1.py::test_export_invalid_format_rejected` |
| **TC-Sec-11** | `AMG-SR-010` | Security | Submit meeting with XSS script tags (`<script>alert('xss')</script>`) and SQL injection strings (`'; DROP TABLE meetings; --`). | Inputs are safely persisted via SQLAlchemy parameterized queries without SQL injection; strings stored and retrieved literally without executing scripts. | `tests/test_api_v1.py::test_security_xss_and_sql_injection_in_meeting_inputs` |
| **TC-Sec-12** | `AMG-SR-006` | Security | Simulate database failure during audio upload transaction. | Transaction rolls back cleanly; partial file on disk is deleted; no orphan audio records remain in the database. | `tests/test_api_v1.py::test_security_database_rollback_on_upload_error` |

---

## 3. Full Requirements Traceability Matrix (Backend Scope)

| SRS Requirement ID | Requirement Description | Corresponding Test Cases in STP | Automated Test Implementation |
|---|---|---|---|
| **AMG-F-010** | Create meeting with details | `TC-Mtg-01` | `test_create_meeting_returns_meeting_id`, `test_create_meeting_rejects_a_missing_or_blank_title` |
| **AMG-F-011** | Upload meeting recording | `TC-Aud-01`, `TC-Aud-05`, `TC-Aud-06` | `test_upload_starts_a_job`, `test_upload_errors`, `test_oversized_upload_is_rejected_and_cleaned_up` |
| **AMG-F-013** | Validate & normalise audio | `TC-Aud-03` | `test_preprocess_converts_to_16k_mono`, `test_corrupt_audio_rejected`, `test_empty_file_rejected` |
| **AMG-F-014** | Processing status reporting | `TC-Aud-04` | `test_status_before_any_audio`, `test_status_reports_the_running_job`, `test_status_after_a_restart_offers_a_retry` |
| **AMG-F-020** | Speech-to-text conversion | `TC-Tr-01` | `test_transcribe_returns_text_and_timestamps`, `test_job_creates_minutes` |
| **AMG-F-040** | Generate structured minutes | `TC-Min-01` | `test_job_creates_minutes`, `test_minutes_response_structure` |
| **AMG-F-041** | Editable minutes | `TC-Min-02` | `test_saving_minutes_bumps_the_version` |
| **AMG-F-043** | Version history & conflict handling | `TC-Min-04`, `TC-Min-07` | `test_saving_minutes_version_conflict_rejection` |
| **AMG-F-044** | Export to Word, PDF, Markdown | `TC-Min-05`, `TC-Min-08` | `test_export_markdown`, `test_export_docx`, `test_export_pdf`, `test_export_invalid_format_rejected` |
| **AMG-NF-007** | Maintainability & test coverage (≥ 70%) | `TC-Mnt-01` | `pytest --cov=app --cov=minutes --cov-branch` (Measured: 76%) |
| **AMG-SR-006** | File validation & malicious upload defense | `TC-Sec-06`, `TC-Aud-05`, `TC-Aud-06`, `TC-Sec-12` | `test_security_path_traversal_filename_neutralized`, `test_security_extension_spoofing_handled_by_transcription` |
| **AMG-SR-010** | Injection prevention (SQLi, XSS) | `TC-Sec-10`, `TC-Sec-11` | `test_security_xss_and_sql_injection_in_meeting_inputs` |

---

## 4. Traceability Gaps / Items for Future Phases

The following SRS requirements currently lack backend implementations and are intentionally flagged:
- `AMG-F-001` (User Registration & Login): Authentication module not yet implemented.
- `AMG-F-002` (Role-Based Access Control): Authorization checks not yet implemented.
- `AMG-F-003` (Account Lockout): Dependent on authentication.
- `AMG-F-045` (Email Sharing): SMTP delivery service not yet implemented in backend.
- `AMG-F-050` / `AMG-F-051` (Action Item Dashboard & Reminders): Scheduled reminder daemon not yet implemented.
- `AMG-SR-001` (TLS 1.2+ configuration): Handled by deployment reverse proxy, not backend code.
