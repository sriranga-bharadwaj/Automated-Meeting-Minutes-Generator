# Transcription evaluation

Used to produce `docs/Transcription_Evaluation_Report.md` (accuracy, speed and bad-input checks).

> **Note: the audio is synthetic.** The 4 clips currently in `eval/recordings/` were generated with an AI voice (espeak-ng), not recorded by people. Real speech may score a higher word error rate than the reported figures.

## 1. Record 3 to 5 short recordings (1 to 3 minutes each)
Write what you will say first, then read it aloud, so you have an exact reference text.
Use different conditions, for example:

| Name | Condition |
|---|---|
| `quiet_room` | one person, quiet room |
| `noisy_room` | background noise (fan, street, music) |
| `fast_speaker` | speaking quickly |
| `two_speakers` | two people taking turns |
| `meeting_style` | a realistic meeting with names, decisions and "X will do Y by Friday" |

## 2. Put the files in `eval/recordings/`
For each recording, add the audio and a text file with the same name:

    eval/recordings/quiet_room.m4a
    eval/recordings/quiet_room.txt     <- exactly what was said

Audio can be mp3, wav, m4a, ogg, webm or mp4, up to 25 MB. A recording without a `.txt` is
still transcribed but gets no accuracy score.

## 3. Run (from the `backend` folder, with the virtual environment active)

    python scripts/evaluate_transcription.py

The first run downloads the Whisper model (about 150 MB). Useful options:

    --language hi            force Hindi (or en) instead of auto-detect
    --skip-edge-cases        only the recordings
    --edge-cases-only        only the bad-input checks (no recordings needed)

If accuracy is below the 15% target, try a bigger model and run again (PowerShell):

    $env:WHISPER_MODEL_SIZE="small"

## 4. Results
- `docs/Transcription_Evaluation_Report.md`: the report (commit this).
- `eval/transcripts/`: the transcript of each recording.
