# Transcription Evaluation Report

- Generated: 2026-11-19 12:36
- Machine: Windows 11, Python 3.12.10
- Model: faster-whisper 1.2.1, size `base`, device `cpu`, compute `int8` (model load took 2.1 s)
- Target (Test Plan exit criteria): word error rate (WER) <= 15%

## Accuracy and speed

Combined average over all 5 files: 10.2%. This mixes synthetic and real audio, so read the two tables below separately.

### Synthetic clips (AI voice, espeak-ng)

> **Note: these 4 clips are synthetic.** They were generated with an AI voice (espeak-ng), not recorded by people. Real speech scores higher, as the real recording below shows.

**Average WER over the 4 synthetic clips: 8.9%: PASS**

| Recording | Length (s) | Time taken (s) | Speed (x real time) | Language | Segments | WER | Result |
|---|---|---|---|---|---|---|---|
| fast_speaker.m4a | 38.3 | 4.5 | 0.12 | en | 16 | 7.4% | PASS |
| noisy_room.mp3 | 60.1 | 11.5 | 0.19 | en | 17 | 12.1% | PASS |
| quiet_room.wav | 60.1 | 12.1 | 0.20 | en | 20 | 6.7% | PASS |
| two_speakers.wav | 69.7 | 12.1 | 0.17 | en | 18 | 9.4% | PASS |

### Real recording (human voice)

Conditions: recorded on a phone, quiet speaking voice, about 69 seconds, one speaker reading a script (`eval/recordings/Recording.txt`). Whisper `base` model, language auto-detected (en).

| Recording | Length (s) | Time taken (s) | Speed (x real time) | Language | Segments | WER | Result |
|---|---|---|---|---|---|---|---|
| Recording.m4a | 69.0 | 13.7 | 0.20 | en | 12 | 15.4% | FAIL (target 15%) |

Same recording with the larger `small` model (`WHISPER_MODEL_SIZE=small`, CPU, int8), run on 19-Nov-2026:

| Model | WER | Time taken (s) | Speed (x real time) | Result |
|---|---|---|---|---|
| `base` | 15.4% | 13.7 | 0.20 | FAIL |
| `small` | 11.7% | 30.8 | 0.45 | PASS |

With `small`, the remaining differences are: Karthik heard as "Kartik" (3 times), "the report" as "a project", "when" as "and", "Thursday" as "Tuesday", "internet" as "internals", two "the" as "a", "morning" dropped, and the sentence "Asha, can you update the test document?" dropped. Still one recording only, so 11.7% against the 15% target is not a wide margin. The evaluation script does not pass attendee names to the model, but the app does (`initial_prompt`).

Full web UI run with `small` (attendees Ravi, Meera, Asha, Karthik; minutes engine `llm`, 112 s; `base` run took 115 s). The stored transcript spells "Karthik" correctly. Comparison with the script:

| Item | `base` model | `small` model |
|---|---|---|
| Decisions listed (script has 2) | 0 | 2 (move the database to a faster server; keep a recorded backup video) |
| Karthik arranges server by Tuesday | right (24-Nov) | right (24-Nov) |
| Asha updates test document by Thursday | task "Operate the test document", deadline 24-Nov (wrong) | task right, deadline 24-Nov (wrong, Thursday heard as Tuesday) |
| Meera prepares opening slides | task "opening sites", deadline 20-Nov (not said) | task right, deadline 20-Nov (not said) |
| Ravi prepares demo slides by next Friday | 20-Nov | 20-Nov |
| Karthik records backup video by Wednesday | task "(deadline: Getting a step)", no date | task right, 25-Nov (right) |

With `small`: 2 of 2 decisions, 5 of 5 action items, 5 of 5 owners right, 3 of 5 deadlines right (Asha wrong, Meera's not in the script). "Next Friday" is read as 20-Nov (the day after the 19-Nov meeting); 27-Nov is also a possible reading.

The real recording at `base` misses the 15% target by 0.4 percentage points (162 reference words, 14 differences listed below). Only one real recording was scored. A `Recording_normalized.m4a` was not available, so no normalised version was compared.

Where the transcript differs from the script (after lower-casing and removing punctuation):

| Script | Transcript |
|---|---|
| begin the | be an |
| we have | without |
| Karthik (3 times) | Kartik |
| the report | a project |
| when | and |
| together | to them |
| you update the test | operate that as |
| update the test | operate that as |
| Thursday | Tuesday |
| agreed that | have created |
| will | and |
| slides | sites |
| morning | (dropped) |

Names (Karthik), a deadline (Thursday heard as Tuesday) and the words "update the test document" were the most damaging errors for the minutes. They come from the quiet phone recording and the base model, not from the evaluation script.

Speed below 1.0 means faster than real time.

## Transcripts

### fast_speaker.m4a

```
Good morning everyone, let's start the print review. Today we have Ravi, Mir and Asha, first, the demo. Ravi sent the editor almost finished, and we decided to use a pre-recorded demo for the final review instead of a live one, because the internet in the lab is unreliable. Mir can you confirm the room booking? Mir will book the seminar hall by Wednesday. Next, testing. Asha reported that the upload feature works for short recordings, but long recordings failed twice last week. We agreed that Asha will fix the long recording problem by Friday. Ravi will also finish the export award by next Monday. On the dark humans, we decided to submit the test report at the end of this month. Mir will collect the coverage reports from everyone. Does anyone have any other questions? No, great. Let's meet again on Thursday morning. Thank you all.
```

### noisy_room.mp3

```
Good morning everyone, let's start the screen review. Today we have Ravi, Mirra and Asher. First, the demo. Ravi said the editor is almost finished, and we decided to use a pre-recorded demo for the final review instead of a live one, because the internet in the lab is unreliable. Mirra, can you confirm the room working? Mirra will work the seminar all by Wednesday. Next, testing. Asher reported that the upload feature works for short recordings, but long recordings failed twice last week. We agreed that Asher will fix the long recording problem by Friday. Ravi will also finish the export at work by next Monday. On the knockupons, we decided to submit a test report at the end of this month. Mirra will collect a camera in reports from everyone. Does anyone have any other questions? No, great. Let's meet again on Thursday morning. Thank you all.
```

### quiet_room.wav

```
Good morning everyone, let's start the print review. Today we have Ravi, Mir and Ashah. First, the demo. Ravi said the editor is almost finished, and we decided to use a pre-recorded demo for the final review instead of a live one, because the internet in the lab is unreliable. Mir, can you confirm the room booking? Mir will book the seminar hall by Wednesday. Next, testing. Ashah reported that the upload feature works for short recordings, but long recordings failed twice last week. We agreed that Ashah will fix the long recording problem by Friday. Ravi will also finish the export award by next Monday. On the documents, we decided to submit the test report at the end of this month. Mir will collect the coverage reports from everyone. Does anyone have any other questions? No. Great. Let's meet again on Thursday morning. Thank you all.
```

### Recording.m4a

```
Good afternoon everyone, let's be an weekly project meeting today without Ravi Meera, Asha and Kartik. Let's start with the status. Ravi said the login page is finished and he is now working on a project screen. Meera mentioned that the database is slow and many people upload files to them. We decided to move the database to a faster server before the final demo. Kartik will arrange the new server by Tuesday. Asha can operate that as document. Asha will operate that as document by Tuesday. Next, the presentation. We have created each member and speak for a few minutes. Meera will prepare the opening sites and Ravi will prepare the demo slides by next Friday. One risk is that the lab internet may fail during the demo. So, we decided to keep a recorded backup video. Kartik will record the backup video by Wednesday. Is there anything else? No, good. Let's meet again next Monday. Thank you everyone.
```

### two_speakers.wav

```
Good morning everyone, let's start the sprint review. Today we have Ravi, Mirra and Shah. First, the demo. Ravi said the editor is almost finished, and we decided to use a pre-recorded demo for the final review instead of a live one, because the internet in the lab is unreliable. Mirra, can you confirm the room booking? Mirra will book the seminar hall by Wednesday. Next, testing. A Shah reported that the upload feature works for short recordings, but long recordings failed twice last week. We agreed that a Shah will fix the long recording problem by Friday. Ravi will also finish the export toward my next Monday. On the dark humans, we decided to submit the test report at the end of this month. Mirra will collect the coverage reports from everyone. Does anyone have any other questions? No? Great. Let's meet again on Thursday morning. Thank you all.
```

## Bad-input checks

| Case | Expected | Got | Result |
|---|---|---|---|
| Unsupported file type (.txt) | UnsupportedAudioFormatError | UnsupportedAudioFormatError: Unsupported audio format '.txt'. Supported formats: .m4a, .mp3, .mp4,  | PASS |
| Empty file | AudioPreprocessingError | AudioPreprocessingError: The audio file is empty. | PASS |
| Corrupt file named .mp3 | AudioPreprocessingError | AudioPreprocessingError: Could not decode audio file (Error opening input files: Invalid data f | PASS |
| File that does not exist | FileNotFoundError | FileNotFoundError: Audio file not found: C:\Users\user\AppData\Local\Temp\ammg_edge_34g67 | PASS |
| Silent audio (no speech) | empty transcript | empty transcript | PASS |

5 of 5 bad-input checks passed.
