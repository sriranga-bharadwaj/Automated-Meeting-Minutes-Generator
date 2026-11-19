# System Validation Report

Executed: 2026-11-18. Browser-driven run of the real app (React frontend on :5173, FastAPI backend on :8000) by `frontend/scripts/system-validation.mjs` (Playwright, Chrome). Screenshots and downloads are in `docs/system-validation/`. Raw data: `docs/system-validation/results.json`.

> **The audio is synthetic.** The clips were generated with an AI voice (espeak-ng), not recorded by people. Real speech may transcribe worse and give worse minutes.

## 1. Environment

| Item | Value |
|---|---|
| OS | Windows 11 Home Single Language 10.0.26200 |
| Python | 3.12.10 (virtual environment `.venv`) |
| Node | v24.22.1 |
| Browser automation | Playwright (`@playwright/test` ^1.65.1) driving installed Google Chrome |
| Speech-to-text | faster-whisper 1.2.1, model `base`, CPU, int8 |
| Minutes engine | **LLM** through Ollama (`qwen2.5:7b`, Ollama running). Confirmed from the stored minutes (`engine = llm`) for the two_speakers run. For the quiet_room run the stored record has no `engine` field because the UI save in TC04 replaced it (see bug B5); Ollama was running for both runs and the minutes have the same shape and quality, but I only verified the field for two_speakers. |
| Backend | `uvicorn app.main:app --port 8000`, branch `docs/system-validation` (from `origin/main`) |

## 2. Test cases

| ID | Steps | Expected | Actual | Result | Screenshot |
|---|---|---|---|---|---|
| quiet-TC01 | Fill title, date, agenda and attendees Ravi, Meera, Asha; click Create meeting | Meeting is created and the audio step opens | Audio step opened | PASS | [form](system-validation/quiet-01-meeting-form.png), [audio step](system-validation/quiet-02-audio-step.png) |
| quiet-TC02 | Upload `quiet_room.wav`, click Upload and generate | Progress screen with stages is shown | "Generating your minutes", Transcribing 20% | PASS | [progress](system-validation/quiet-03-progress.png) |
| quiet-TC03 | Wait for processing | Minutes appear | Minutes shown after 115 s | PASS | [minutes](system-validation/quiet-04-minutes.png) |
| quiet-TC04 | Edit the first topic title | "All changes saved" appears | Shown | PASS | [saved](system-validation/quiet-05-saved.png) |
| quiet-TC06 | Click Word (DOCX) | A file downloads | `minutes.docx`, 37,261 bytes | PASS | [shot](system-validation/quiet-06-export-docx.png), [file](system-validation/downloads/quiet-minutes.docx) |
| quiet-TC07 | Click PDF | A file downloads | `minutes.pdf`, 2,569 bytes | PASS | [shot](system-validation/quiet-07-export-pdf.png), [file](system-validation/downloads/quiet-minutes.pdf) |
| quiet-TC08 | Click Markdown | A file downloads | `minutes.md`, 910 bytes | PASS | [shot](system-validation/quiet-08-export-md.png), [file](system-validation/downloads/quiet-minutes.md) |
| CORRUPT-TC01 | Upload a text file renamed `corrupt.mp3` | Error message and a Retry button | "Processing failed", "Could not decode audio file (Error opening input files: Invalid data found when processing input).", Retry button visible. Retry was not clicked. | PASS | [error](system-validation/corrupt-01-error.png) |
| two-TC01 | Create the meeting again with the same attendees | Audio step opens | Opened | PASS | [shot](system-validation/two-02-audio-step.png) |
| two-TC02 | Upload `two_speakers.wav` | Progress screen | Shown | PASS | [shot](system-validation/two-03-progress.png) |
| two-TC03 | Wait for processing | Minutes appear | Minutes shown after 99 s | PASS | [shot](system-validation/two-04-minutes.png) |
| quiet-EX | Compare minutes with the 6 expected items | All 6 found with correct owner and deadline | 5 of 6 found as expected, with defects (section 3) | **FAIL** | [minutes](system-validation/quiet-04-minutes.png) |
| two-EX | Compare minutes with the 6 expected items | All 6 found with correct owner and deadline | 4 of 6 found, 2 wrong owners (section 3) | **FAIL** | [minutes](system-validation/two-04-minutes.png) |

Notes: ID quiet-TC05 is unused. The edit (TC04) and exports (TC06 to TC08) were run on the quiet_room meeting only. The language selector (English or Hindi) was left at its default and was not tested. Corrupt-file Retry was not clicked.

## 3. Extraction results

Expected items from the script: 2 decisions and 4 action items. "Next Wednesday", "Friday" and "next Monday" were resolved relative to the meeting date 2026-11-18 (a Wednesday), so Wednesday = 2026-11-25, Friday = 2026-11-20, Monday = 2026-11-23.

### quiet_room.wav (minutes title shown: "Print Review Meeting")

| Expected item | Generated | Owner | Deadline | Verdict |
|---|---|---|---|---|
| Decision: use a pre-recorded demo | "Use pre-recorded demo" | n/a | n/a | Found |
| Decision: submit the test report at the end of this month | Not in Decisions. Appears as action item "Submit the test report (deadline: at the end of this month)" and in a topic summary | Unassigned | none | Found only as an action item, wrong type |
| Meera books the seminar hall by Wednesday | "Confirm the room booking" | Meera (correct) | 2026-11-25 (correct) | Found, task wording is the question, not the commitment |
| Asha fixes the long recording problem by Friday | "Fix the long recording problem" | Asha (correct) | 2026-11-20 (correct) | Found |
| Ravi finishes the export to Word by next Monday | "Finish the export award" | Ravi (correct) | 2026-11-23 (correct) | Found, task text garbled by the transcript ("export award") |
| Meera collects the coverage reports | "Collect the coverage reports from everyone" | Meera (correct) | 2026-11-20 (**not in the script**) | Found, deadline invented |

Score: 5 of 6 found as the right kind of item (the end-of-month decision only as an action item). Owners correct on 4 of 4 action items. Deadlines correct on 3 of 4, plus one invented.

### two_speakers.wav (minutes title shown: "Print Review Meeting")

| Expected item | Generated | Owner | Deadline | Verdict |
|---|---|---|---|---|
| Decision: use a pre-recorded demo | "Use pre-recorded demo" | n/a | n/a | Found |
| Decision: submit the test report at the end of this month | Not found as decision or action item | n/a | n/a | **Missing** |
| Meera books the seminar hall by Wednesday | "Book the seminar hall" | **"Mirror"** (wrong) | 2026-11-25 (correct) | Found, owner wrong |
| Asha fixes the long recording problem by Friday | "Fix the long recording problem" | Asha (correct) | 2026-11-20 (correct) | Found |
| Ravi finishes the export to Word by next Monday | "Finish the export" | Ravi (correct) | 2026-11-23 (correct) | Found |
| Meera collects the coverage reports | "Collect the coverage reports" | **"Mirror"** (wrong) | none (correct) | Found, owner wrong |

Score: 4 of 6 found (the end-of-month decision missing, and only 1 of the 2 decisions). Owners correct on 2 of 4 action items. Deadlines correct on 4 of 4.

## 4. Bugs and defects found (not fixed)

| ID | Where | Problem | Likely cause |
|---|---|---|---|
| B1 | Both runs | The second decision (submit the test report at the end of this month) is not listed under Decisions. In quiet_room it is an action item with no owner; in two_speakers it is missing. | Minutes generator (LLM extraction) |
| B2 | two_speakers | Owner "Mirror" for two action items, although the attendee is Meera. The name was misheard ("Mirra") and not matched to an attendee. quiet_room, which heard "Mir", was matched to Meera. | Transcription of the name, and attendee matching |
| B3 | quiet_room | "Collect the coverage reports" has deadline 2026-11-20 that nobody said. | Minutes generator |
| B4 | Both runs | The minutes title is "Print Review Meeting" (from the mis-heard word "sprint"). The title typed in the form ("Sprint review (quiet)", "Sprint review (two)") is not shown. | Minutes generator replaces the user's title with a generated one |
| B5 | quiet_room | After editing and saving in the UI, the stored minutes no longer contain the `engine` field. | Save handler stores the UI shape only |
| B6 | quiet_room | Task text "Confirm the room booking" (the question) instead of "Book the seminar hall"; "Finish the export award" instead of "export to Word". | Transcription errors and LLM wording |
| B7 | Corrupt file | An unsupported-content file with a valid extension is accepted by the upload screen and only fails after upload, in the processing step. The message is raw ("Error opening input files: Invalid data found..."). It works, but is not user friendly. | Validation only checks the extension in the browser |

PDF export (2,569 bytes) was confirmed as a download only. I did not open it to check its content.
