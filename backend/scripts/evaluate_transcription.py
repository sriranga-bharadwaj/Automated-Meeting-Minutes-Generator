"""Measure transcription accuracy and speed on real recordings, and write a report.

Put recordings in  eval/recordings/  and, next to each one, a text file with exactly what
was said (same name, .txt):

    eval/recordings/quiet_room.m4a
    eval/recordings/quiet_room.txt      <- reference text you read aloud

Run from the backend folder:

    python scripts/evaluate_transcription.py

It writes  docs/Transcription_Evaluation_Report.md  and saves each transcript in
eval/transcripts/. Recordings without a .txt are still transcribed (no accuracy score).

Options:
    --folder PATH        recordings folder (default: eval/recordings)
    --language en|hi     force the spoken language instead of auto-detecting
    --out PATH           report file (default: docs/Transcription_Evaluation_Report.md)
    --skip-edge-cases    do not run the bad-input checks
    --edge-cases-only    only run the bad-input checks
"""
from __future__ import annotations

import argparse
import platform
import struct
import sys
import tempfile
import time
import wave
from datetime import datetime
from importlib import metadata
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from app.evaluation import word_error_rate  # noqa: E402

AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".ogg", ".webm", ".mp4"}
WER_TARGET = 0.15  # from the Test Plan exit criteria


def write_silent_wav(path: Path, seconds: int = 3, rate: int = 16000) -> None:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(struct.pack("<h", 0) * (seconds * rate))


def run_edge_cases() -> list[dict]:
    """Bad inputs must give a clear error (or an empty transcript), never a crash."""
    from app.transcription import (
        AudioPreprocessingError,
        UnsupportedAudioFormatError,
        transcribe_audio,
    )

    results = []
    with tempfile.TemporaryDirectory(prefix="ammg_edge_") as tmp:
        tmp = Path(tmp)
        (tmp / "notes.txt").write_text("this is not audio")
        (tmp / "empty.wav").write_bytes(b"")
        (tmp / "corrupt.mp3").write_bytes(b"this is definitely not an mp3 file" * 50)
        write_silent_wav(tmp / "silence.wav")

        cases = [
            ("Unsupported file type (.txt)", tmp / "notes.txt", UnsupportedAudioFormatError),
            ("Empty file", tmp / "empty.wav", AudioPreprocessingError),
            ("Corrupt file named .mp3", tmp / "corrupt.mp3", AudioPreprocessingError),
            ("File that does not exist", tmp / "missing.wav", FileNotFoundError),
            ("Silent audio (no speech)", tmp / "silence.wav", None),
        ]
        for name, path, expected in cases:
            try:
                out = transcribe_audio(str(path))
                if expected is None and not out["text"].strip():
                    results.append({"case": name, "expected": "empty transcript", "got": "empty transcript", "ok": True})
                else:
                    results.append({"case": name, "expected": getattr(expected, "__name__", "empty transcript"),
                                    "got": f"transcript: {out['text'][:40]!r}", "ok": False})
            except Exception as exc:  # noqa: BLE001
                ok = expected is not None and isinstance(exc, expected)
                results.append({"case": name,
                                "expected": getattr(expected, "__name__", "empty transcript"),
                                "got": f"{type(exc).__name__}: {str(exc)[:70]}", "ok": ok})
    return results


def evaluate_recordings(folder: Path, language: str | None, transcripts_dir: Path) -> tuple[list[dict], float]:
    from app.transcription import get_model, transcribe_audio

    files = sorted(p for p in folder.glob("*") if p.suffix.lower() in AUDIO_EXTS)
    if not files:
        return [], 0.0

    started = time.perf_counter()
    get_model()  # load once so model loading is not counted in each recording's time
    load_seconds = time.perf_counter() - started

    transcripts_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for audio in files:
        began = time.perf_counter()
        result = transcribe_audio(str(audio), language=language)
        elapsed = time.perf_counter() - began
        (transcripts_dir / f"{audio.stem}.txt").write_text(result["text"], encoding="utf-8")

        reference_file = audio.with_suffix(".txt")
        wer = None
        if reference_file.exists():
            wer = word_error_rate(reference_file.read_text(encoding="utf-8"), result["text"])

        rows.append({
            "name": audio.name,
            "duration": result["duration"],
            "seconds": elapsed,
            "rtf": elapsed / result["duration"] if result["duration"] else 0.0,
            "language": result["language"],
            "segments": len(result["segments"]),
            "wer": wer,
            "text": result["text"],
        })
    return rows, load_seconds


def build_report(rows, load_seconds, edge_results) -> str:
    from app.transcription import COMPUTE_TYPE, DEVICE, MODEL_SIZE

    try:
        fw = metadata.version("faster-whisper")
    except metadata.PackageNotFoundError:
        fw = "unknown"

    lines = [
        "# Transcription Evaluation Report",
        "",
        f"- Generated: {datetime.now():%Y-%m-%d %H:%M}",
        f"- Machine: {platform.system()} {platform.release()}, Python {platform.python_version()}",
        f"- Model: faster-whisper {fw}, size `{MODEL_SIZE}`, device `{DEVICE}`, compute `{COMPUTE_TYPE}`"
        + (f" (model load took {load_seconds:.1f} s)" if rows else ""),
        f"- Target (Test Plan exit criteria): word error rate (WER) <= {WER_TARGET:.0%}",
        "",
    ]

    if rows:
        scored = [r for r in rows if r["wer"] is not None]
        lines += ["## Accuracy and speed", ""]
        if scored:
            average = sum(r["wer"] for r in scored) / len(scored)
            verdict = "PASS" if average <= WER_TARGET else "FAIL"
            lines += [f"**Average WER: {average:.1%} over {len(scored)} recording(s): {verdict}**", ""]
        lines += ["| Recording | Length (s) | Time taken (s) | Speed (x real time) | Language | Segments | WER | Result |",
                  "|---|---|---|---|---|---|---|---|"]
        for r in rows:
            if r["wer"] is None:
                wer, res = "n/a (no reference)", "-"
            else:
                wer, res = f"{r['wer']:.1%}", "PASS" if r["wer"] <= WER_TARGET else "FAIL"
            lines.append(f"| {r['name']} | {r['duration']:.1f} | {r['seconds']:.1f} | {r['rtf']:.2f} | "
                         f"{r['language']} | {r['segments']} | {wer} | {res} |")
        lines += ["", "Speed below 1.0 means faster than real time.", "", "## Transcripts", ""]
        for r in rows:
            lines += [f"### {r['name']}", "", "```", r["text"] or "(no speech detected)", "```", ""]
    else:
        lines += ["## Accuracy and speed", "", "_No recordings were found in the recordings folder._", ""]

    if edge_results is not None:
        lines += ["## Bad-input checks", "", "| Case | Expected | Got | Result |", "|---|---|---|---|"]
        for e in edge_results:
            lines.append(f"| {e['case']} | {e['expected']} | {e['got']} | {'PASS' if e['ok'] else 'FAIL'} |")
        passed = sum(e["ok"] for e in edge_results)
        lines += ["", f"{passed} of {len(edge_results)} bad-input checks passed.", ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--folder", type=Path, default=ROOT / "eval" / "recordings")
    parser.add_argument("--language", default=None)
    parser.add_argument("--out", type=Path, default=ROOT / "docs" / "Transcription_Evaluation_Report.md")
    parser.add_argument("--skip-edge-cases", action="store_true")
    parser.add_argument("--edge-cases-only", action="store_true")
    args = parser.parse_args()

    rows, load_seconds = ([], 0.0)
    if not args.edge_cases_only:
        rows, load_seconds = evaluate_recordings(args.folder, args.language, ROOT / "eval" / "transcripts")
        if not rows:
            print(f"No recordings found in {args.folder}. See eval/README.md.")
    edge_results = None if args.skip_edge_cases else run_edge_cases()

    report = build_report(rows, load_seconds, edge_results)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nReport written to {args.out}")
    failed = [e for e in (edge_results or []) if not e["ok"]]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
