# Transcription Evaluation Report

- Generated: 2026-11-18 22:39
- Machine: Windows 11, Python 3.12.10
- Model: faster-whisper 1.2.1, size `base`, device `cpu`, compute `int8` (model load took 4.1 s)
- Target (Test Plan exit criteria): word error rate (WER) <= 15%

> **Note: the audio is synthetic.** The 4 clips in `eval/recordings/` were generated with an AI voice (espeak-ng), not recorded by people. Real human speech (accents, hesitations, overlapping talk, real room noise) may score a higher word error rate than the figures below.

## Accuracy and speed

**Average WER: 8.9% over 4 recording(s): PASS**

| Recording | Length (s) | Time taken (s) | Speed (x real time) | Language | Segments | WER | Result |
|---|---|---|---|---|---|---|---|
| fast_speaker.m4a | 38.3 | 13.6 | 0.35 | en | 16 | 7.4% | PASS |
| noisy_room.mp3 | 60.1 | 14.9 | 0.25 | en | 17 | 12.1% | PASS |
| quiet_room.wav | 60.1 | 12.1 | 0.20 | en | 20 | 6.7% | PASS |
| two_speakers.wav | 69.7 | 12.5 | 0.18 | en | 18 | 9.4% | PASS |

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
| File that does not exist | FileNotFoundError | FileNotFoundError: Audio file not found: C:\Users\user\AppData\Local\Temp\ammg_edge_3go69 | PASS |
| Silent audio (no speech) | empty transcript | empty transcript | PASS |

5 of 5 bad-input checks passed.
