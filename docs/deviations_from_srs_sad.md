# Deviations from the SRS and SAD

Project: Automated Meeting Minutes Generator (AMMG)
Prepared by: Swasthik Pamadi (Member 3, minutes generator)
Date: 2026-11-20

## 1. Purpose and sources

This document lists where the delivered system differs from the SRS
(`SRS_AMMG`) and the SAD (`SAD_AMMG`). The status of each requirement is taken
from `docs/Requirements_Status.md` (checked 19-Nov-2026 against the code, the
automated tests and a live browser run). The accuracy figures come from
`docs/accuracy_report.md`.

## 2. Summary

Most requirements were delivered, including login, three roles, the admin
console, email sharing, the action dashboard, deadline reminders, export to
Word, PDF and Markdown, version history, AES-256 encryption at rest and
audit logging. Two requirements are not delivered, six are partly delivered,
and several non-functional requirements were measured only partly or not at all.

## 3. Requirements not delivered

| ID | Requirement | What exists instead | Reason | Impact |
|---|---|---|---|---|
| F-021 | Automatic speaker identification | The transcript editor lets a person type a speaker name for each segment, with the attendees offered as suggestions | The app cannot tell speakers apart by voice. The SAD planned pyannote.audio, which needs a gated model download, a Hugging Face token and PyTorch | Transcripts have no speaker labels unless typed by hand. The minutes generator finds owners from names spoken in the meeting and the attendee list |
| F-001 (part) | Email verification when registering | Registration and login work with Argon2id password hashes | Test case TC-Auth-01 asks for it; it was not built | An account can be registered without the email address being confirmed |

## 4. Requirements partly delivered

| ID | Requirement | What is missing |
|---|---|---|
| SR-001 | TLS 1.2 or higher | HTTPS works with a development certificate (TLS 1.2 accepted, TLS 1.1 refused, HSTS sent) and `FORCE_HTTPS=true` redirects HTTP to HTTPS. A real certificate and secured service-to-service links are the deployer's job. The default run is plain HTTP on localhost |
| SR-006 | Upload validation and virus scan | Content type, file signature, size, decode check and random file names are done. The ClamAV scan runs only when ClamAV is installed. It is not installed on the test machine, so it was skipped and tested only with a stand-in |
| F-023 | Language selection (English/Hindi) | The selector exists and its value is passed to Whisper. No Hindi recording was ever run |
| F-031 | Decisions | Decisions are found, but the model sometimes misses one |
| F-034 | Deadlines | Weekdays and "tomorrow" are turned into dates. "Next Friday" is deliberately left in the task text. A mis-heard weekday gives a wrong date |
| F-035 | Confidence scores | Shown for each item, but not computed per item: the keyword fallback gives 50% and the AI model 100% |

Other differences inside delivered requirements:
- F-011 (upload): the size limit is 500 MB on the `/api/v1` route and 25 MB on
  the older route that the web UI uses. This is to be settled when the
  duplicate API is removed.
- F-020 (speech to text): the default Whisper model `base` scores a word error
  rate of 15.4% on the real phone recording, which misses the 15% target. The
  `small` model scores 11.7%. The README recommends `small` for longer meetings.
- F-012 (browser recording): pause and resume were not tested.
- F-042 (source linking): topics are matched to segments by shared words, so an
  item with no match gets no link.
- F-045 (email sharing) and F-051 (reminders): tested against a local test mail
  server, not a real mail provider. Reminders need SMTP and an email address for
  the owner in the attendee list.
- F-060 (job monitoring): the admin console shows job state, but there is no
  queue or retry control.
- SR-007: rate limits are kept in memory, so they work for one server process only.
- SR-008: the audit log is in the same database, so someone with database
  access could rewrite the whole chain.
- SR-002: meeting titles and attendee names are not encrypted. If the
  encryption key is lost, the data cannot be read.

## 5. Non-functional requirements

| ID | Requirement | Status |
|---|---|---|
| NF-001 | Performance | Measured on 5 recordings (0.07 to 0.45 times real time), not the 10 in the plan |
| NF-002 | Accuracy | Word error rate measured (see F-020). Minutes accuracy is now measured by script, see section 7 |
| NF-003 | Reliability | Not measured |
| NF-004 | Usability | Not measured (no survey) |
| NF-005 | Scalability | Done: 100 users at once, 0 failed requests of 4000; 20 jobs submitted together all finished, one at a time (27 minutes in total) |
| NF-006 | Compatibility | Tested in Chrome only |
| NF-007 | Maintainability | Test suites exist; the frontend coverage report covers `utils.ts` only |
| NF-008 | Accessibility | An axe check runs in the browser test; no manual audit |

## 6. Changes from the planned design (SAD)

| Area | Planned (SAD) | Delivered | Effect |
|---|---|---|---|
| Database | PostgreSQL for structured data | SQLite file `backend/ammg.db` through SQLAlchemy | Simpler setup, but one writer at a time. The load test needed a larger connection pool and SQLite WAL mode |
| Object storage | MinIO/S3 for audio and exports | Recordings stored on the local disk, encrypted with AES-256-GCM | No separate storage service to run. Not suited to several servers |
| Queue and cache | Redis | None. Jobs are processed one after another by the application | 20 jobs submitted together all finished, the last after 26.7 minutes. There is no queue or retry control (F-060) |
| Diarization stage | `pyannote.audio` between speech recognition and the minutes extractor | Not built (F-021) | Transcripts have no speaker labels unless typed by hand |
| Minutes generation | Local instruction-tuned LLM, with spaCy and dateparser | `qwen2.5:7b` through Ollama with transcript chunking and a keyword fallback when Ollama is not running. Relative dates are turned into dates by rules in the code. spaCy and dateparser are not used; those rules do their work | Follows the plan (a local model). Nothing is sent to a third party (SR-009) |
| Speech to text | faster-whisper | faster-whisper on the CPU, `base` by default, `small` recommended | As planned. Word error rate: 15.4% with `base`, 11.7% with `small` |
| Security | TLS, JWT, roles | JWT with 30-minute access tokens and rotating refresh tokens, Argon2id hashes, account lockout, rate limits, hash-chained audit log | Delivered, with the limits in section 4 |

## 7. Minutes accuracy (Test Plan target: action-item F1 of 0.75 or better)

Measured with `backend/minutes/evaluate.py` on 5 labelled transcripts in the
format the app produces (timestamped text, no speaker labels), with
`qwen2.5:7b` through Ollama on an NVIDIA GPU (about 52 tokens/s, about 10 s per
transcript). Final run, 20-Nov-2026:

| Group | Transcripts | Action-item precision | Recall | F1 |
|---|---|---|---|---|
| Held-out (not used for prompt tuning) | 3 | 1.00 | 0.92 | 0.96 |
| Development (prompt tuned on these) | 2 | 1.00 | 1.00 | 1.00 |
| All | 5 | 1.00 | 0.95 | 0.97 |

The held-out F1 was 0.96 in each of three repeated runs. In the final run,
owner accuracy on matched items was 1.00, deadline accuracy 1.00, and all 5
labelled decisions were found. Scores on the development transcripts varied
between runs (0.82 to 1.00), and the F1 over all 5 transcripts was 0.92 in one
of the three runs and 0.97 in the other two. Quote the held-out figure.

The first version of the held-out transcripts had a speaker name at the start
of each line, which the app's own transcripts do not have. They were rewritten
without names. The held-out F1 stayed at 0.96, deadline accuracy changed from
0.91 to 1.00, and the one missed item moved from meeting_3 to meeting_5.

Limitations: the sample is small (12 held-out action items, so one miss changes
recall by about 0.08). The transcripts are clean written text made by the team,
so speech-recognition errors and overlapping speech are not included. Real
meetings are likely to score lower. Matching uses word overlap, so a correct
item with different wording can count as a miss. The Test Plan asks for 20
annotated meetings; 5 were used.

## 8. Added during testing

- An automated accuracy evaluation tool with separate development and
  held-out transcript groups, and its report in `docs/`.
