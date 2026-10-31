# Meeting minutes generator (Member 3)

Turns a meeting transcript into structured minutes: summary, topics,
decisions and action items (with owners and deadlines when they are stated).

## Setup

1. Install Ollama (https://ollama.com) and pull the model:
   `ollama pull qwen2.5:7b`
2. `python3 -m venv .venv && source .venv/bin/activate`
3. `pip install -r requirements.txt`

## Usage

```python
from minutes import generate_minutes, segments_to_transcript, MinutesGenerationError

# Member 2's segments (start in seconds + text) -> transcript text
transcript = segments_to_transcript(segments)

try:
    minutes = generate_minutes(transcript, progress=lambda done, total: print(done, total))
except MinutesGenerationError as e:
    ...  # empty transcript, Ollama not running, or the model gave invalid output

minutes.model_dump()   # plain dict, ready to return as JSON
```

## Input format

Plain text, one line per segment: `[HH:MM:SS] spoken text`.
No speaker names are needed. `segments_to_transcript()` builds this from
faster-whisper segments or from dicts with `start` and `text`.

## Output (`MeetingMinutes`, see minutes/schema.py)

| field | type | notes |
|---|---|---|
| title | str | |
| summary | str | 2-4 sentences |
| participants | list[str] | names that appear in the transcript |
| topics | list | `{title, summary, start_time}`, start_time in seconds or null |
| decisions | list | `{decision, context}` |
| action_items | list | `{task, owner, deadline}`: owner and deadline are null when not stated, deadline is free text such as "Wednesday" or "before the review" |

## Speed: run it as a background job

A 30-minute meeting takes several minutes on a CPU-only laptop. Do NOT make the
HTTP request wait for the result. Start a job, then let the UI poll for status.
`progress(done, total)` is called after each chunk, so the UI can show a bar.

## Configuration

`MINUTES_MODEL` selects the Ollama model (default `qwen2.5:7b`).
`qwen2.5:14b` is more thorough but about twice as slow.

## Tests

```
pytest tests/test_chunking.py tests/test_transcript.py tests/test_schema.py   # fast
pytest tests/test_generator.py                                                # runs the model, a few minutes
```