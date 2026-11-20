# Test case results: minutes generator (Member 3)

Date: 20-Nov-2026. The rows follow the results layout of Appendix A in the
Software Test Plan, so they can be copied into it. Accuracy figures come from
`docs/accuracy_report.md` (5 labelled transcripts without speaker labels,
qwen2.5:7b through Ollama on an NVIDIA GPU, about 10 s per transcript).

| Test case | Requirement | Actual result | Status | Date | Evidence |
|---|---|---|---|---|---|
| TC-Min-01 | AMG-F-040 | Full run of the quiet-room recording: the minutes appeared after 115 s. The exported minutes contain title, date, attendees, agenda, key discussions, decisions and an action table (task, owner, deadline, status). The summary sentence stored with the minutes does not appear in the exported files. The list of required sections in the SRS was not re-checked. | PASS (partial) | 20-Nov-2026 | System_Validation_Report.md (quiet-TC03); system-validation/downloads/quiet-minutes.pdf |
| TC-Min-02 | AMG-F-041 | The first topic title was edited in the browser and "All changes saved" appeared. The edited title is in the exported Word and PDF files, so the save reached the database. Add, delete and move are covered by backend tests. Reloading the page after editing the minutes was not run in the browser. | PASS (partial) | 20-Nov-2026 | System_Validation_Report.md (quiet-TC04); backend/tests/test_features.py; Requirements_Status.md (F-041) |
| TC-Min-05 (replaces the existing result) | AMG-F-044 | Word, PDF and Markdown files were downloaded and all three opened. Word and PDF show the same title, date, attendees, agenda, 3 topics (with the edited title), 1 decision and 5 action items with owner, deadline and status. Defect: in the Word file the decision is numbered "4." instead of "1." because the list numbering continues from the topics list. The PDF is correct. | PASS (partial; Word numbering defect) | 20-Nov-2026 | system-validation/downloads/quiet-minutes.docx and quiet-minutes.pdf; System_Validation_Report.md (quiet-TC06 to TC08) |
| TC-NLP-01 | AMG-F-030 | In the saved results for all 5 sample transcripts (10 topics) every topic has a title, a summary and a start time. There is no end time (time range). The check was a script over docs/accuracy_results.json. Topic recall was not measured, because the evaluation script scores only action items and decisions. | PASS (partial) | 20-Nov-2026 | docs/accuracy_results.json |
| TC-NLP-02 | AMG-F-031 | 5 labelled decisions in 5 transcripts (3 held-out): all 5 found and none extra, so precision and recall 1.00. The plan asks for 20 decisions. On real audio the model sometimes misses a decision (Requirements_Status.md). | PASS (partial) | 20-Nov-2026 | docs/accuracy_report.md; Requirements_Status.md (F-031) |
| TC-NLP-03 | AMG-F-032 | Held-out (3 transcripts, 12 action items): precision 1.00, recall 0.92, F1 0.96, the same in 3 runs. Target 0.75 met. One item in meeting_5 was not found. All 5 transcripts (20 items): F1 0.97 (0.92 in one run). The plan asks for 40 action items and 20 were used. The transcripts are written text, not audio. On the real recording with the small model, 5 of 5 action items were found. | PASS (partial) | 20-Nov-2026 | docs/accuracy_report.md; docs/accuracy_results.json; Requirements_Status.md (F-032) |
| TC-NLP-04 | AMG-F-033 | Owner accuracy on matched held-out items is 1.00, with no speaker labels in the transcripts. A task with no owner counts as correct when the label also has none. A named owner ("Priya will send the report") works. "I'll do it" giving the speaker was not tested: the app produces no speaker labels (F-021 not implemented). A mis-heard name can still give a wrong owner. | PASS (partial) | 20-Nov-2026 | docs/accuracy_report.md; Requirements_Status.md (F-033) |
| TC-NLP-05 | AMG-F-034 | Weekday names and "tomorrow" are turned into dates from the meeting date; the quiet-room minutes show 2026-11-20, 2026-11-23 and 2026-11-25. "Next Friday" is left in the task text by design, so the planned 09-10-2026 is not produced. "By 30th" was not tested. Deadline accuracy on matched held-out items was 1.00 in the final run (text match). A mis-heard weekday gives a wrong date. | PASS (partial; "next Friday" left as text, deviation) | 20-Nov-2026 | docs/accuracy_report.md; Requirements_Status.md (F-034); system-validation/downloads/quiet-minutes.pdf |
| TC-NLP-06 | AMG-F-035 | A confidence score is shown for each item, but it is a fixed value, not computed per item: the keyword fallback gives 50% and the AI model 100%. Ambiguous sentences therefore do not score below 0.6 when the AI model is used. Highlighting of items below 0.6 was not tested. | FAIL (fixed scores, not per item) | 20-Nov-2026 | Requirements_Status.md (F-035) |
| TC-Acc-01 | AMG-NF-002 | Minutes accuracy: held-out action-item F1 is 0.96 against the target of 0.75 (met), on 3 held-out transcripts, identical in 3 runs. 5 transcripts were run, not the 20-meeting set (noisy, accented, multi-speaker), which was not built. Word error rate is covered by TC-Tr-01: average 8.9% on 4 synthetic clips with base; on the real phone clip 15.4% with base and 11.7% with small (Requirements_Status.md). | PASS (partial) | 20-Nov-2026 | docs/accuracy_report.md; Transcription_Evaluation_Report.md |

## Notes

- Defect found today: the Word export numbers the decision "4." (TC-Min-05).
- Existing defect: TC-Min-06 fails because one invalid address blocks sharing
  to all addresses.
- Limits of the accuracy tests: the transcripts are clean written text made by
  the team, the held-out sample is small (one missed item changes recall by
  about 0.08), and scores on the development transcripts varied between runs.
- The first version of the held-out transcripts had speaker names on every
  line. They were rewritten without names to match the app's input; the
  held-out F1 stayed at 0.96.
